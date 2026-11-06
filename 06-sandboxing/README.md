# Module 06: Sandboxing

## The Concept

Module 03's gate decides which *statements* may run. It says nothing about *where they
read*. `SELECT * FROM read_csv('C:/Users/you/.ssh/id_rsa')` is a perfectly good SELECT.
Module 04 even demonstrated it. To fix that we do not parse paths out of SQL (a losing
game: globs, `..`, backslashes, UNC paths, junctions, functions that take a file). We ask
DuckDB to enforce the rule itself, in its file layer, where every function has to go
through it.

```
 SQL ──► [gate: one read-only statement] ──► DuckDB ──► [file layer: allowed folders only] ──► disk
            Module 03                                      this module
```

## Three Settings, In This Order

```python
con.execute("SET allowed_directories = ?", [[folder + "/"]])   # 1. where reading is OK
con.execute("SET enable_external_access = false")              # 2. everything else is off
con.execute("SET lock_configuration = true")                   # 3. no SQL can change 1 or 2
```

1. **`allowed_directories`**: folders (or prefixes) that stay readable even when external
   access is off.
2. **`enable_external_access = false`**: disables reading any other path, URLs (so
   `read_csv('https://...')` and `httpfs`), `INSTALL` and `LOAD` of extensions, and
   `ATTACH` of other files.
3. **`lock_configuration = true`**: a one-way door that freezes *every* setting. Afterwards
   `SET enable_external_access = true` fails with "the configuration has been locked".
   The gate already rejects `SET`, and this makes the sandbox hold *even if the gate had a
   bug*, which `main.py` checks by calling `con.execute("SET ...")` directly, bypassing the
   gate. Be precise about what the lock adds: DuckDB (2.0) already refuses to switch
   external access back on ("Cannot enable external access while database is running") and
   to change `allowed_directories` once access is off, so those two are protected twice.
   The lock covers the rest (`threads`, `memory_limit`, `temp_directory`, ...). It is
   belt and braces, and I measured that rather than assumed it (Break It, challenge 2).

**The order is not optional.** Once step 2 has run, DuckDB refuses to change
`allowed_directories` ("Cannot change allowed_directories when enable_external_access is
disabled"), and you also cannot pass it in `duckdb.connect(config=...)` ("before the
database is started"). So: connect, set the folder, turn access off, lock.

Two more settings keep the process tidy: `autoinstall_known_extensions` and
`autoload_known_extensions` off (nothing is fetched behind your back) and a private
`temp_directory` for spill files (otherwise DuckDB creates a `.tmp` folder in the current
directory).

## The Trailing Slash

```python
self.folder + "/"
```

The docs call `allowed_directories` entries "directories and directory prefixes", which
raises the "same-prefix sibling" worry: would allowing `.../data` also allow `.../data2`?
We spell the entry with a trailing slash so the answer is no by construction. In the DuckDB
version tested here (2.0.0), DuckDB appends the slash itself (`current_setting` shows
`.../data/` even when you pass `.../data`), so the explicit slash is redundant today. It
costs nothing, and `main.py` creates a `data2/neighbour.csv` next to the allowed `data`
folder and asserts it cannot be read, so a future DuckDB that changed this would fail the
test rather than silently widen the sandbox.

## What DuckDB Gets Right (Verified, Not Assumed)

The attack list in `attacks()` runs against a real sandbox and expects every one to fail:

| Attack | Outcome |
|--------|---------|
| `read_csv('<abs path elsewhere>')` | Permission Error, "file system operations are disabled" |
| `read_text('C:/Windows/win.ini')` (or `/etc/passwd`) | refused |
| `'../outside/secret.csv'` (relative) | refused |
| `<allowed>/../outside/secret.csv` (absolute `..`) | refused: DuckDB normalises the path |
| `<sibling folder with the same prefix>` | refused (trailing slash) |
| `glob('<elsewhere>/*')` | refused: even listing is blocked |
| `read_csv('https://example.com/x.csv')` | refused |
| `INSTALL httpfs`, `ATTACH ...`, `COPY ... TO` | refused (gate and DuckDB) |
| `EXPLAIN ANALYZE COPY ...` | refused by the gate; no file appears |

Directory junctions and symlinks that point out of the folder are also refused (the full
server tests this with a real Windows junction); the tutorial server keeps the attack list
short, the finished one tests more.

## The Convenience Rewriter Must Not Become a Hole

`absolutise` turns `'t.csv'` into an absolute path. It also checks the result is *inside*
the folder (`Path(full).resolve()...startswith(folder + "/")`) before rewriting. That is
belt and braces only: if the rewriter were wrong, DuckDB would still refuse. Never make a
convenience feature the only thing between the agent and the disk.

## A Timeout That Really Stops the Query

```python
timer = threading.Timer(self.timeout, stop)   # stop() sets a flag, then cur.interrupt()
```

`cursor.interrupt()` makes the running query raise. The flag distinguishes our timeout from
other errors, so the message can say "stopped after the 30s time limit" instead of an
obscure `InterruptException`. The cursor is closed in `finally`, and `main.py` checks the
server still answers `SELECT 1` afterwards. The test query is a cross join of two
100-million-row ranges, which would otherwise run for ages.

Be honest about what this does not do: it bounds *time*, not memory. A query can still use
RAM until the timeout, and the whole allowed folder is readable. Do not allow a folder with
secrets in it.

## The Finished Server

`main.py --serve --dir DATA` is the complete minimal server: gate (03), friendly names
(02), capped results (05), error conversion (04) and the sandbox. Three tools:
`list_files`, `describe_file`, `query`. The real `duckdb-mcp` adds `profile_file`,
`sample_file`, `explain_query`, multiple folders, globs, CSV/JSON output and a configurable
cap, but not a different design.

## Run It

```bash
python 06-sandboxing/main.py
```

Expected: `in-process attacks: all refused`, then a stdio session where reading a file
outside the folder is an error, then `OK`.

→ [Next: Module 07, Testing It For Real](../07-testing-it-for-real/README.md)
