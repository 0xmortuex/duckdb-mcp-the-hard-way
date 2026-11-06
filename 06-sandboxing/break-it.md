# Break It: Sandboxing

## Challenge 1: Wrong order

Move `SET enable_external_access = false` above `SET allowed_directories = ...` and run
`main.py`. What error do you get, from which line?

**Hint:** "Cannot change allowed_directories when enable_external_access is disabled".
The constructor fails immediately, which is a good thing: a misordered sandbox that
silently allowed nothing, or everything, would be far worse.

## Challenge 2: Forget the lock

Delete the `lock_configuration` line. Which attacks in `attacks()` still fail? Call
`sb.con.execute("SET enable_external_access = true")` and then read the outside file.

**Hint:** All the SQL-level attacks still fail, because the gate rejects `SET`. The direct
`con.execute("SET enable_external_access = true")` *also* still fails, with a different
message ("Cannot enable external access while database is running"): DuckDB refuses it on
its own. So in this DuckDB version the lock is redundant for those two settings, and only
the first assertion in `attacks()` (that the message contains "locked") fails. The lock
still freezes every other setting, such as `memory_limit` and `threads`. Remove a layer, and
check *which* promise you lose rather than assuming. Here the answer was "less than I
expected", and that is worth knowing.

## Challenge 3: Drop the trailing slash

Remove `+ "/"` from the `allowed_directories` value. Which attack from the table starts
working?

**Hint:** On DuckDB 2.0.0 the answer is: none. DuckDB appends the slash itself, so
`data2/neighbour.csv` stays unreadable (print `current_setting('allowed_directories')`
to see the slash it added). The explicit slash is insurance against a version that
doesn't. The attack list is how you would find out, which is why `data2` is in it. Try the
variant of `datax/` too.

## Challenge 4: A symlink or junction

Inside the allowed folder create a directory link to the outside folder
(`mklink /J escape ..\outside` on Windows, `ln -s ../outside escape` elsewhere), then query
`'escape/secret.csv'`. Does it work?

**Hint:** It is refused: DuckDB checks the real, resolved location. Expect that a
sandbox which only compared path *strings* would fail this one, which is why the
comparison is delegated to the engine. The finished `duckdb-mcp` has this as a test.

## Challenge 5: The time limit and the finally block

Remove `timer.cancel()` and `cur.close()` from the `finally` block, then run 100 quick
queries in a loop. What leaks?

**Hint:** Each query leaves a live timer thread for `timeout` seconds, and each fired timer
would interrupt a cursor that is long finished or, worse, reused. Cleanup in `finally` is
the difference between a server that runs for a minute and one that runs for a month.

→ [Next: Module 07](../07-testing-it-for-real/README.md)
