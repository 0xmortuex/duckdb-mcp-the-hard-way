# Break It: Testing It For Real

## Challenge 1: Weaken the server, watch the suite

In `06-sandboxing/main.py`, delete the `lock_configuration` line. Does `run_escape_suite`
notice? Delete the `EXPLAIN_PREFIX` inner check instead. Does it notice that?

**Hint:** The first: no. The suite attacks through `run()`, where the gate already rejects
`SET`, so it stays green. The lock only matters when the gate is bypassed, and Module 06's
`attacks()` covers that with a direct `con.execute`. The second: yes, via the
`explain analyze copy` entry and the "a file was written" check. A suite finds only what it
looks for, so add a test whenever you add a layer.

## Challenge 2: Add an attack

Add a 14th attempt to `escape_attempts`: reading `data` through a path with mixed case
(`.../DATA/ok.csv`) and one with a trailing dot or space. Is it a leak, or just allowed?

**Hint:** Windows paths are case-insensitive, so the first one *is* the allowed file under a
different spelling. That is correct to allow. Decide what a "leak" is (reading something
outside the folder) before writing the test, or the suite will cry wolf and be ignored.

## Challenge 3: Make the stdio test miss an error

Change the Module 06 tool wrapper to `raise ValueError(str(e))` instead of `ToolError`.
Which assertion in `test_stdio` fails?

**Hint:** `"read-only" in res.content[0].text`. The client only receives "Error executing
tool query". This is the cheapest regression test in the course and the one most likely to
save you.

## Challenge 4: Prove it streams

Replace `fetchmany(cap + 1)` with `fetchall()[:cap]` in Module 06's `run`. Does
`test_big_files` fail on a 1,000,000-row file on your machine? How many rows would it take?

**Hint:** At a million rows it may only get slower, and may still pass the 5 second bound. Try
100 million rows of generated data (`range(100000000)`) to see it fail. A threshold test
needs input big enough that the wrong implementation clearly breaks it; check that yours does by running
it against the wrong implementation, just as `test_the_tests` does for the sandbox.

→ Back to the [course index](../README.md)
