# Module 07: Testing It For Real

## The Concept

A sandbox that has not been attacked is a belief. This module adds no feature; it tests the
server from Module 06 four ways, and the fourth, testing the tests, is the one most
projects skip.

`main.py` loads `06-sandboxing/main.py` *by path* (`importlib.util.spec_from_file_location`).
That is the one place a tutorial module depends on another, and it is deliberate: the
subject of this module is Module 06's server.

## 1. Real Files, Real Escapes

`make_world()` builds three folders: `data` (allowed), `data2` (a sibling that shares the
name prefix) and `outside` (holds a secret). `escape_attempts()` is a dict of 13 named SQL
strings: absolute path elsewhere, system file, relative and absolute `..`, sibling folder,
glob, URL, `COPY`, `EXPLAIN ANALYZE COPY`, `INSTALL`, `ATTACH`, two statements.

```python
leaks = run_escape_suite(sandbox, world)     # names of attempts that were NOT refused
assert leaks == []
```

Two details matter:

- **It checks the type of the refusal.** An attempt that fails with an `AttributeError` is
  recorded as a leak ("wrong error type"), not a pass. A crash is not a defence, and it hides
  a bug.
- **It checks the world.** After the suite, `dropped.csv` must not exist. A safety test that
  only inspects return values misses the write that "succeeded" quietly. (This is exactly how
  `EXPLAIN ANALYZE COPY` slips through: it returns a plan *and* writes a file.)

## 2. Test the Tests

Passing proves nothing if the suite cannot fail. So `test_the_tests` builds `Leaky`, a
subclass of the server's `Sandbox` that has the same gate and API but a connection with
**none** of the three sandbox settings, and runs the same suite against it:

```
leaky sandbox leaks: ['absolute path elsewhere', 'bare quoted path elsewhere',
                      'absolute traversal', 'same-prefix sibling folder', 'glob outside']
```

The assertions say which must appear. Notice what does *not* appear: `COPY`, `ATTACH`,
`INSTALL` and the relative `..` are still refused, because the statement gate and the path
check are independent layers. The experiment therefore doubles as a map of which layer
stops which attack.

This is a hand-made mutation test. For a security property it is cheap, quick, and the
only evidence the suite would notice a regression.

## 3. A Big File

The generator writes two 1,000,000-row files (CSV and Parquet) with DuckDB itself (about
0.2 s) and checks, for each:

- `SELECT *` returns exactly 1,000 rows, `truncated` is true, in well under 5 seconds
  (typically tens of milliseconds): it streams;
- `count(*)` is 1,000,000 and `max(id)` is 999,999: the cap affects *output*, never what
  aggregates see.

The time assertion is the streaming test. Materialising a million rows in Python would take
seconds and hundreds of megabytes. The full project additionally runs the capped query in a
child process and asserts its peak memory is a fraction of that.

## 4. The Handshake

The only test that shows what a client really sees: launch the server as a subprocess, speak
MCP to it, and check:

- `initialize` returns the server name;
- `list_tools` returns exactly the expected tools, each with a non-empty description;
- a normal query returns a table;
- a blocked statement and an outside-the-folder read come back as `is_error` with the
  *instructive text intact*, "read-only", "File access is limited".

That last point is the Module 04 lesson, enforced: if someone later raises a plain
`ValueError`, this test fails, because the client would only see "Error executing tool".

## What Is Not Tested Here

Honest limits, since this is a security tool:

- It does not test every DuckDB function that opens a file. The sandbox covers the file
  layer, not each function, which is why it was chosen. A new DuckDB version could add a
  function that behaves differently; the weekly CI run is how you find out.
- It checks time and row counts for streaming, not peak memory.
- It runs on one platform per CI job. Windows paths (backslashes, drive letters, UNC) are
  where file sandboxes tend to break, so CI runs this tutorial on Windows too.

## Run Everything

```bash
python 07-testing-it-for-real/main.py   # this module
python verify.py                        # all seven, as CI does
```

You now have the shape of `duckdb-mcp`. The finished project is this design plus more
tools, more tests, packaging and CI. The code to read next is its `sandbox.py`.

→ Back to the [course index](../README.md)
