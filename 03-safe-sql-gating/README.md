# Module 03: Safe SQL Gating

## The Concept

Handing an agent a SQL tool means handing it every statement the engine speaks. DuckDB
speaks a lot: `CREATE`, `INSERT`, `ATTACH`, `INSTALL`, `COPY ... TO`, `EXPORT DATABASE`,
`PRAGMA`, `SET`. For analysing files you need exactly one family: queries that read.

So before anything executes, the server asks one question: **is this a single read-only
statement?** The hard part is answering it without being fooled.

## Don't Match Strings; Ask the Parser

The tempting gate:

```python
if not sql.strip().lower().startswith("select"): reject
```

fails in both directions. It *accepts* `SELECT 1; DROP TABLE t` (two statements) and it
*rejects* legitimate queries that start with `WITH`, `FROM range(3)`, `DESCRIBE` or
`SUMMARIZE`. It can also be confused by a leading comment such as `/* select */ DROP ...`.

DuckDB exposes its own parser:

```python
[s.type.name for s in con.extract_statements(sql)]    # ['SELECT'], ['COPY'], ['SELECT', 'DROP'], ...
```

The first thing `main.py` does is print what it calls "the table of truth", 18 statements
and their classification. Things worth noticing:

| Statement | DuckDB calls it |
|-----------|-----------------|
| `WITH t AS (...) SELECT ...`, `FROM range(3)`, `VALUES (1)` | `SELECT` |
| `DESCRIBE ...`, `SUMMARIZE ...`, `SHOW TABLES` | `SELECT` |
| `EXPLAIN ...` | `EXPLAIN` |
| `COPY`, `ATTACH`, `EXPORT`, `SET`, `PRAGMA`, `CALL` | their own types |
| `INSTALL x`, `LOAD x` | both `LOAD` |

So the allowlist is one word, `SELECT`, plus `EXPLAIN` handled separately. DuckDB's
friendly dialect (FROM-first queries, DESCRIBE, SUMMARIZE) arrives for free because the
parser already files them under SELECT. `SELECT 1; SELECT 2` is two statements, so
"exactly one" is a simple `len(kinds) == 1`.

A bonus: `extract_statements` raises on invalid SQL, so syntax errors surface here with
DuckDB's message, before anything runs.

## Why Gating Is Needed At All

Step 3 of `main.py` runs `COPY (SELECT 1 AS x) TO '<tmp>/written.csv'` on a plain
connection and the file appears. Module 06's folder sandbox does **not** stop this: writing
into an *allowed* folder is allowed. Read confinement and write prevention are different
jobs, and the gate owns the second one.

## The EXPLAIN Hole

The obvious allowlist is `{"SELECT", "EXPLAIN"}`, because explaining a query is harmless.
It is called `naive_gate` in `main.py`, and step 4 breaks it:

```sql
EXPLAIN ANALYZE COPY (SELECT 1 AS x) TO '/data/pwned.csv'
```

`extract_statements` says `['EXPLAIN']`, the naive gate waves it through, and DuckDB *runs*
the COPY, because `ANALYZE` means "execute and report timings". The file is created. This
was found by testing, not by reading docs, which is the point of Module 07.

The fix is to judge what is *inside* the EXPLAIN:

```python
EXPLAIN_PREFIX = re.compile(r"^\s*explain(?:\s+analyze\b)?(?:\s*\([^)]*\))?\s*", re.I)
inner = statement_types(con, EXPLAIN_PREFIX.sub("", sql, count=1))
if inner != ["SELECT"]: reject
```

It strips `EXPLAIN`, an optional `ANALYZE`, and an optional parenthesised option list such as
`(ANALYZE)`, then asks the parser about the rest. Using the regex only to find the *start*
of the inner statement, and the parser to classify it, keeps the decision with the parser.

## Messages That Tell the Agent What To Do

`"COPY statements are blocked: this server is read-only. Allowed: SELECT / WITH / VALUES /
FROM, DESCRIBE, SUMMARIZE, SHOW and EXPLAIN."`

The agent can fix its own mistake from that message. "Access denied" would produce another
blind retry.

## Run It

```bash
python 03-safe-sql-gating/main.py
```

→ [Next: Module 04, The MCP Tool Wrapper](../04-the-mcp-tool-wrapper/README.md)
