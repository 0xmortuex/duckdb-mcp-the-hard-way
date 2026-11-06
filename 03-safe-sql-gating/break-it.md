# Break It: Safe SQL Gating

## Challenge 1: Fool the string gate

Write a three-line `startswith("select")` gate and find a statement that passes it but
should not (two ways), and a legitimate query it wrongly rejects (two ways). Then show that
`check_sql` gets all four right.

**Hint:** `SELECT 1; DROP TABLE t` and `SELECT * FROM t; COPY ...` pass the string gate.
`WITH ...`, `FROM range(3)`, `DESCRIBE ...` and a query with a leading comment fail it.

## Challenge 2: Sneak a write past the real gate

Try these against `check_sql`. Which are accepted? Which should be?

```sql
SELECT * FROM query('COPY (SELECT 1) TO ''x.csv''')
CREATE TEMP TABLE t AS SELECT 1
SELECT nextval('seq')
PIVOT 'orders.csv' ON country USING count(*)
```

**Hint:** The `query()` table function only accepts a single SELECT, so DuckDB itself
refuses the nested COPY ("Expected a single SELECT statement"). `CREATE ...` is blocked by
type. `nextval` needs a sequence, which cannot exist because nothing can create one.
PIVOT is classified as `MULTI` (it can create enum types), so the gate rejects a useful
statement. That is a deliberate, documented loss in the real server: writing a `GROUP BY`
is an easy workaround and the gate stays one word long.

## Challenge 3: Strip the EXPLAIN check

Make `check_sql` accept any statement whose type is `EXPLAIN`. Run step 4. How do you know the
write happened, and why does the exception-free run matter?

**Hint:** The file exists afterwards. The query "succeeded" and returned a plan, so a test
that only looked at the tool's return value would pass. Tests for safety must look at the
*world* (does the file exist?), not at the answer.

## Challenge 4: Parenthesised options

DuckDB accepts `EXPLAIN (ANALYZE) COPY ...` and `EXPLAIN ANALYZE COPY ...`. Remove the
`(?:\s*\([^)]*\))?` part of the regex and test both. What happens, and is it a security
problem or only an annoyance?

**Hint:** Without it the prefix strip leaves `(ANALYZE) COPY ...`, which does not parse.
`statement_types` raises `SqlRejected` for the syntax error, so it fails *closed*:
annoying (a valid EXPLAIN is refused) but not a hole. Prefer designs where a mistake
rejects rather than accepts.

→ [Next: Module 04](../04-the-mcp-tool-wrapper/README.md)
