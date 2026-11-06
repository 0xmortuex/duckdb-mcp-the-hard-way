# Module 02: Reading Files

## The Concept

The agent should say `SELECT * FROM 'orders.csv'` and have it work, whether that file is a
CSV, a gzipped TSV or a Parquet file, and wherever in the folder tree it lives. Three small
pieces make that true:

```
 'orders.csv'  --absolutise-->  'C:/data/orders.csv'  --reader_sql-->  read_csv('C:/data/orders.csv')
   (what the agent types)         (if the file exists)                   (what DuckDB runs)
```

## One Reader Per Format

```python
def reader_sql(path):
    kind = data_kind(path)
    if kind == "parquet": return f"read_parquet({sql_literal(path)})"
    if kind == "json":    return f"read_json_auto({sql_literal(path)})"
    if kind in ("csv", "tsv"): return f"read_csv({sql_literal(path)})"
```

- **TSV needs no special case.** `read_csv` sniffs the delimiter, so a tab-separated file
  just works. `main.py` asserts `id` comes out as BIGINT from a TSV.
- **`read_json_auto` handles both layouts**: a JSON array (`[{...}, {...}]`) and
  newline-delimited JSON (one object per line). Callers never need to know which they have.
- **`.gz` is transparent.** `data_kind("old.csv.gz")` strips the `.gz` and classifies the
  rest; DuckDB decompresses by extension. Note it is `.csv.gz` that counts, not a bare
  `.gz`, and Parquet is excluded because it compresses internally.
- **Unsupported files fail early** with the list of supported extensions, instead of a
  parser error from deep inside DuckDB.

## sql_literal: Never Paste a Path Into SQL Raw

```python
def sql_literal(text):
    return "'" + text.replace("'", "''") + "'"
```

A file called `o'brien.csv` would end the SQL string early. In SQL, the escape for a quote
inside a string is two quotes. `main.py` reads `o'brien.csv` to prove it. Table-function
arguments are normally literals, so this quoting is the tool you have.

## list_data_files

`os.walk` plus the `data_kind` filter, returning forward-slash relative paths, sorted:
`['archive/old.csv.gz', 'doc.json', ...]`. Two small decisions:

- Hidden folders (`.git`, `.venv`) are skipped, because the agent never wants those.
- Paths are *relative to the folder*. They are shorter, they do not leak the user's home
  directory into every message, and they are exactly what `absolutise` accepts back.

## absolutise: Friendly Names

The agent writes `'people.csv'`. DuckDB would look relative to the process's current
directory, which is wherever the client launched the server. So the server finds every
quoted literal in the SQL and, if it names a data file that **exists** in the allowed
folder, swaps in the absolute path.

```python
QUOTED = re.compile(r"'((?:[^']|'')*)'|\"((?:[^\"]|\"\")*)\"")
```

The regex understands `''` as an escaped quote inside a literal, so `'it''s.csv'` is one
literal. The important design choice is **only rewrite when the file exists**. A literal
like `'ghost.csv'` or `'hello'` is left alone, so `WHERE name = 'hello'` is untouched and a
missing file produces DuckDB's own error (Module 04 improves its wording).

The known trade-off, stated honestly: `WHERE name = 'orders.csv'` *will* be rewritten if
`orders.csv` exists. A regex cannot tell a table position from a value position. The real
server documents this and notes `'orders' || '.csv'` as the workaround. This function is
**convenience, not security**: Module 06's sandbox is what enforces where files can be
read, whatever the rewriter does.

## Run It

```bash
python 02-reading-files/main.py
```

Expected: the file list, a rewritten query with an absolute path, the unsupported-file
error, then `OK`.

→ [Next: Module 03, Safe SQL Gating](../03-safe-sql-gating/README.md)
