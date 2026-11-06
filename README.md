# DuckDB MCP Server: The Hard Way

Build an MCP server that lets an AI agent run SQL over your local CSV, Parquet and JSON
files, and make it safe enough that you would actually point it at a folder. Start from
`duckdb.connect()` and end with a sandbox you have tried to break on purpose.

At the end you will have built [duckdb-mcp](https://github.com/0xmortuex/duckdb-mcp)
yourself, in about 250 lines, and you will understand the two things most "SQL for your
agent" tutorials skip: **what a database engine will do if you let it**, and **how to
shape results for a reader with a small context window**.

## Why This Exists

The usual demo hands the model a `run_sql(query)` tool and a database connection. That is
fine until you remember what a SQL engine can do:

- DuckDB reads *any file the process can see*: `read_csv('C:/Users/you/.ssh/id_rsa')`.
- It reads URLs, installs extensions from the internet, attaches other databases.
- It writes files: `COPY ... TO`, `EXPORT DATABASE`, and, surprisingly,
  `EXPLAIN ANALYZE COPY ...`, which looks like a harmless "explain" and is not.
- A `SELECT *` on a 10 GB file will happily try to answer.

A useful data tool for an agent is mostly about saying *no* in the right places, and
saying it in words the agent can act on.

## Who This Is For

- Developers who have built a "hello world" MCP server and want a real one
- Anyone who wants an agent to analyse local data without handing over the disk
- Anyone curious how much DuckDB can do with nothing installed but `pip install duckdb`

**Prerequisites:** Python and some SQL. No DuckDB knowledge needed.

```bash
pip install -r requirements.txt      # or: uv pip install -r requirements.txt
python verify.py
```

## Modules

| # | Module | What You'll Build |
|---|--------|-------------------|
| 01 | [DuckDB Basics](01-duckdb-basics/) | An in-memory database that treats files as tables, DESCRIBE/SUMMARIZE, and why `fetchmany` beats `fetchall` |
| 02 | [Reading Files](02-reading-files/) | One reader per format, a file lister, and friendly names (`FROM 'orders.csv'`) |
| 03 | [Safe SQL Gating](03-safe-sql-gating/) | Letting DuckDB's parser decide what a statement is, and the `EXPLAIN ANALYZE COPY` hole |
| 04 | [The MCP Tool Wrapper](04-the-mcp-tool-wrapper/) | Three tools over real stdio, descriptions as instructions, and errors the agent can read |
| 05 | [Output Shaping](05-output-shaping/) | A row cap that streams, a truncation notice, markdown/CSV/JSON, and cell limits |
| 06 | [Sandboxing](06-sandboxing/) | `allowed_directories`, `enable_external_access`, `lock_configuration`, a timeout, and 11 attacks |
| 07 | [Testing It For Real](07-testing-it-for-real/) | An escape suite, a test of the tests, a million-row file and a live stdio handshake |

Each module contains:
- **`README.md`**: the concepts and the design decisions
- **`main.py`**: a working, commented implementation of that stage. It asserts every
  claim the README makes, and prints `OK` only if they all hold
- **`break-it.md`**: challenges that break your own code, with hints

## How To Use This Course

**Option A: Build along.** Read the modules in order, run each `main.py`, then do the
break-it challenges.

**Option B: Reference.** Each `main.py` stands alone (Module 07 loads Module 06's file by
path, on purpose, because it tests that server).

**Option C: Use the finished tool.** `pip install duckdb-mcp` is the full version of what
Module 06 assembles: more tools, glob and multi-folder support, profile and explain tools.

## Every Module Is Verified

```bash
python verify.py          # all seven
python verify.py 03 06    # just these
```

CI runs it on Linux and Windows on every push and weekly, so the code in this course can't
silently stop working when DuckDB or `mcp` changes.

## Architecture Overview

```
 AI agent (Claude Code, Claude Desktop, ...)
        |  MCP over stdio: JSON-RPC tool calls                  <- Module 04
        v
 +-------------------------------------------------------+
 | MCP server: tools, docstrings, ToolError messages     |       <- Module 04
 |   gate    one SELECT-type statement, EXPLAIN checked  |       <- Module 03
 |   names   'orders.csv' -> absolute path (if it exists)|       <- Module 02
 |   shape   fetchmany(cap + 1), notice, md/csv/json     |       <- Module 05
 |   limits  timeout, interrupt()                        |       <- Module 06
 +-------------------------------------------------------+
        |  SQL
        v
 DuckDB (in memory)  allowed_directories + external access off + locked   <- Module 06
        |
        v
 your data folder only: csv, tsv, parquet, json, ndjson
```

## Key Design Principles

**1. Two layers, because each has a hole the other covers.** DuckDB's sandbox stops reads
outside the folder but allows writes inside it. The statement gate stops writes but knows
nothing about paths. Neither alone is enough.

**2. Let the parser parse.** `sql.lower().startswith("select")` is fooled by comments and
by `SELECT 1; DROP TABLE t`. `extract_statements()` is not.

**3. Never compute what you will not show.** Fetch `cap + 1` rows. The extra row tells you
the result was cut, with no `COUNT(*)` over a billion rows.

**4. Errors are instructions.** "Permission denied" is a dead end. "File access is limited
to C:/data. Call list_files" is the next step.

**5. Test the tests.** A security suite that has never failed has not proven anything.
Module 07 removes the sandbox and checks that the suite notices.

## Tech Stack

- **Language:** Python 3.10+
- **Engine:** DuckDB (in-memory, no extensions)
- **Protocol:** MCP over stdio
- **Dependencies:** `mcp`, `duckdb`, `anyio`

## License

MIT. Use it, modify it, ship it.

---

Built by [0xmortuex](https://github.com/0xmortuex)
