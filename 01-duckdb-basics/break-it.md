# Break It: DuckDB Basics

## Challenge 1: fetchall on a big result

Change `fetchmany(11)` in `main.py` to `fetchall()` and run it against
`range(50000000)`. What happens to the run time and to your memory use? Then try
`range(500000000)` if you dare.

**Hint:** `fetchall()` has to materialise every row as a Python tuple. A few hundred bytes
each times fifty million is gigabytes. The SQL was never slow; the Python was.

## Challenge 2: A path with a backslash

On Windows, build the CSV path with `os.path.join` and no `.replace("\\", "/")`, then put
it inside `read_csv('...')`. Does it still work? Now try a path with an apostrophe in a
folder name (`C:/Users/o'brien/orders.csv`).

**Hint:** Backslashes are fine in DuckDB paths, so the first one works. The apostrophe
ends the SQL string early and you get a syntax error, or worse, SQL you did not write.
Module 02's `sql_literal` fixes that by doubling the quote.

## Challenge 3: Wrong guess about types

Edit a copy of `orders.csv` so row 40 has `amount` set to `n/a`. Run the DESCRIBE query.
What type is `amount` now, and what happens to `SUMMARIZE`'s min and max?

**Hint:** On this 40-row file the sniffer sees every row, so one bad value turns the whole
column into VARCHAR, and `max(amount)` becomes an alphabetical max (`n/a`, with `116.45`
as the "min"). On a huge file the sniffer only samples, so a bad value outside the sample
instead fails mid-scan with a conversion error. Either way, an agent should call
`describe_file` before it does arithmetic.

## Challenge 4: Two cursors

Open two cursors on one connection, start a 50-million-row query on the first and do a
`SELECT 1` on the second before fetching from the first. Does it work?

**Hint:** Yes. Cursors are independent result streams over one in-memory database. That
independence is what lets Module 06 interrupt one runaway query and keep serving others.

→ [Next: Module 02](../02-reading-files/README.md)
