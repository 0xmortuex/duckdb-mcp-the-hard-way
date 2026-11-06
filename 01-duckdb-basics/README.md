# Module 01: DuckDB Basics

## The Concept

DuckDB is a SQL database that runs *inside your process*, like SQLite, but built for
analysis: columnar storage, vectorised execution, and, the part that matters here, the
ability to treat a file as a table without importing it.

```
 your Python process
 +-----------------------------+
 |  duckdb.connect(":memory:") |   no server, no database file, no setup
 |        |                    |
 |   SELECT ... FROM 'x.csv' --+--> reads the file while the query runs
 +-----------------------------+
```

For an agent tool this is ideal. There is nothing to install or configure besides
`pip install duckdb`, nothing persistent to corrupt, and a CSV the user already has is
instantly queryable.

## Files Are Tables

```python
con = duckdb.connect(":memory:")
con.execute("SELECT country, count(*) FROM read_csv('orders.csv') GROUP BY country")
```

- `":memory:"` keeps the whole database in RAM and throws it away on exit. No file means
  nothing to write by accident.
- `read_csv(...)` is a *table function*. It sniffs the delimiter, the header and the column
  types from the data, so there is no `CREATE TABLE` step. In `main.py` the `placed_at`
  column comes out as `DATE` and `amount` as `DOUBLE` without being told.
- `FROM 'orders.csv'` is a shortcut ("replacement scan"): a quoted name that is not a table
  is read by file extension. Module 02 builds on this.

## DESCRIBE and SUMMARIZE Are Just Queries

```sql
DESCRIBE SELECT * FROM 'orders.csv'    -- column_name, column_type, null, key, ...
SUMMARIZE 'orders.csv'                 -- min, max, approx_unique, avg, quartiles, null_percentage
```

They return ordinary rows, so the tools that tell an agent what a file contains need no
special code. `main.py` checks that the blank `amount` in row 13 shows up as
`null_percentage == 2.5` (1 of 40). SUMMARIZE also hints at the next lesson: it scans the
file, so on a huge file it is not free.

## Streaming: execute() Starts, fetch Pulls

This is the most important thing in the module.

```python
cur = con.cursor()
cur.execute("SELECT i, i * 2 FROM range(50000000) t(i)")   # starts the query
first = cur.fetchmany(11)                                  # pulls 11 rows
```

DuckDB produces rows in chunks as you ask for them. Asking for 11 of 50,000,000 takes
about a millisecond. `fetchall()` would build 50 million Python tuples and, for a real
file, either exhaust memory or run for minutes. The rest of the server is built around one
rule: **never call `fetchall()` on a user's query.** Module 05 turns it into a row cap.

Use `con.cursor()` rather than the connection directly. Each cursor is an independent
query on the same database, which later lets the server interrupt one query without
touching others.

## Run It

```bash
python 01-duckdb-basics/main.py
```

Expected: the per-country counts, the schema, `amount nulls: 2.50`, and `OK`.

→ [Next: Module 02, Reading Files](../02-reading-files/README.md)
