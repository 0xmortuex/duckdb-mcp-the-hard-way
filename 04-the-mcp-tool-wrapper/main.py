"""Module 04: The MCP tool wrapper. Three tools, and errors an agent can act on.

WARNING: this module's server is gated (read-only SQL) but NOT sandboxed. Its SQL can still
read any file on your disk. Module 06 fixes that. Do not point a real agent at this one.

Run: python 04-the-mcp-tool-wrapper/main.py            (starts the server and drives it over stdio)
     python 04-the-mcp-tool-wrapper/main.py --serve --dir DATA   (just the server)
"""

from __future__ import annotations

import argparse
import asyncio
import functools
import os
import re
import sys
import tempfile
from collections.abc import Callable
from typing import Any, TypeVar

import duckdb
from mcp import ClientSession
from mcp.client.stdio import StdioServerParameters, stdio_client
from mcp.server.mcpserver import MCPServer
from mcp.server.mcpserver.exceptions import ToolError

HERE = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(HERE, "..", "data")


class ToolFailure(Exception):
    """Something the agent did wrong or can fix. The message is written for the agent."""


# ---- the pieces from Modules 02 and 03, shortened ------------------------------------

SUFFIXES = (".csv", ".tsv", ".parquet", ".json", ".ndjson", ".jsonl")
QUOTED = re.compile(r"'((?:[^']|'')*)'")
EXPLAIN_PREFIX = re.compile(r"^\s*explain(?:\s+analyze\b)?(?:\s*\([^)]*\))?\s*", re.IGNORECASE)


def check_sql(con: duckdb.DuckDBPyConnection, sql: str) -> None:
    try:
        kinds = [s.type.name for s in con.extract_statements(sql)]
    except duckdb.Error as e:
        raise ToolFailure(f"SQL syntax error: {e}") from e
    if len(kinds) != 1:
        raise ToolFailure(f"Send exactly one SQL statement per call (got {len(kinds)}).")
    if kinds[0] == "EXPLAIN":
        inner = [s.type.name for s in con.extract_statements(EXPLAIN_PREFIX.sub("", sql, count=1))]
        if inner != ["SELECT"]:
            raise ToolFailure("EXPLAIN is only allowed on a SELECT query.")
    elif kinds[0] != "SELECT":
        raise ToolFailure(f"{kinds[0]} statements are blocked: this server is read-only.")


def absolutise(sql: str, folder: str) -> str:
    def repl(m: re.Match[str]) -> str:
        text = m.group(1).replace("''", "'")
        full = os.path.join(folder, text)
        if text.lower().endswith(SUFFIXES) and os.path.isfile(full):
            return "'" + os.path.abspath(full).replace("\\", "/").replace("'", "''") + "'"
        return m.group(0)

    return QUOTED.sub(repl, sql)


# ---- the server -----------------------------------------------------------------------

mcp = MCPServer(
    "duckdb-tutorial",
    instructions="Query data files with SQL. Call list_files first, then query.",
)
CON = duckdb.connect(":memory:")
FOLDER = DATA
F = TypeVar("F", bound=Callable[..., Any])


def tool(fn: F) -> F:
    """Register fn as an MCP tool, turning ToolFailure into a message the client can see.

    MCPServer forwards only a ToolError's message. Any other exception reaches the
    agent as a bare 'Error executing tool X', which is a dead end.
    """

    @functools.wraps(fn)
    def wrapper(*args: Any, **kwargs: Any) -> Any:
        try:
            return fn(*args, **kwargs)
        except ToolFailure as e:
            raise ToolError(str(e)) from e

    mcp.tool()(wrapper)
    return fn


@tool
def list_files() -> str:
    """List the data files you can query (CSV, TSV, Parquet, JSON, NDJSON).

    Call this first. The paths it prints can be used directly in SQL: SELECT * FROM 'orders.csv'.
    """
    names = sorted(n for n in os.listdir(FOLDER) if n.lower().endswith(SUFFIXES))
    if not names:
        raise ToolFailure(f"No data files in {FOLDER}.")
    return "\n".join(names)


@tool
def query(sql: str) -> str:
    """Run one read-only SQL statement (DuckDB dialect) over the data files.

    Name files like SELECT * FROM 'orders.csv'. Returns rows as plain text, at most 20.
    """
    sql = absolutise(sql, FOLDER)
    check_sql(CON, sql)
    cur = CON.cursor()
    try:
        cur.execute(sql)
    except duckdb.Error as e:
        raise ToolFailure(str(e)) from e
    rows = cur.fetchmany(20)
    cols = [d[0] for d in cur.description]
    return "\n".join([" | ".join(cols), *(" | ".join(str(v) for v in r) for r in rows)])


@mcp.tool()
def query_unwrapped(sql: str) -> str:
    """Teaching only: the same failure without the ToolError wrapper."""
    raise ValueError("this message never reaches the agent")


# ---- a client that behaves like an agent -----------------------------------------------


async def drive() -> None:
    params = StdioServerParameters(
        command=sys.executable, args=[os.path.abspath(__file__), "--serve", "--dir", DATA]
    )
    async with stdio_client(params) as (read, write), ClientSession(read, write) as session:
        await session.initialize()

        tools = {t.name: t for t in (await session.list_tools()).tools}
        print("tools:", sorted(tools))
        assert {"list_files", "query"} <= set(tools)
        # The docstring IS the description the agent reads.
        assert "Call this first" in (tools["list_files"].description or "")
        # The type hints became a JSON schema.
        assert tools["query"].input_schema["required"] == ["sql"]

        res = await session.call_tool("list_files", {})
        assert not res.is_error and "orders.csv" in res.content[0].text  # type: ignore[union-attr]

        res = await session.call_tool(
            "query",
            {"sql": "SELECT country, count(*) AS n FROM 'orders.csv' GROUP BY 1 ORDER BY n DESC, 1"},
        )
        text = res.content[0].text  # type: ignore[union-attr]
        print(text)
        assert text.splitlines()[0] == "country | n" and text.splitlines()[1] == "US | 22"

        # Errors that tell the agent what to do next.
        res = await session.call_tool("query", {"sql": "DROP TABLE orders"})
        print("blocked:", res.content[0].text)  # type: ignore[union-attr]
        assert res.is_error and "read-only" in res.content[0].text  # type: ignore[union-attr]

        res = await session.call_tool("query", {"sql": "SELECT * FROM 'nope.csv'"})
        assert res.is_error and "nope.csv" in res.content[0].text  # type: ignore[union-attr]

        # The same kind of failure WITHOUT the wrapper: the useful text is gone.
        res = await session.call_tool("query_unwrapped", {"sql": "SELECT 1"})
        print("unwrapped:", res.content[0].text)  # type: ignore[union-attr]
        assert res.is_error and "never reaches" not in res.content[0].text  # type: ignore[union-attr]

        # The flaw Module 06 fixes: the gate only controls WHAT runs, not WHERE it reads.
        with tempfile.TemporaryDirectory() as other:
            secret = os.path.join(other, "secret.csv").replace("\\", "/")
            with open(secret, "w", encoding="utf-8") as fh:
                fh.write("password\nhunter2\n")
            res = await session.call_tool("query", {"sql": f"SELECT * FROM read_csv('{secret}')"})
            print("outside the data folder:", res.content[0].text.splitlines())  # type: ignore[union-attr]
            assert "hunter2" in res.content[0].text  # type: ignore[union-attr]
    print("OK")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--serve", action="store_true", help="run the MCP server on stdio")
    ap.add_argument("--dir", default=DATA)
    args = ap.parse_args()
    global FOLDER
    FOLDER = args.dir
    if args.serve:
        # stdout IS the protocol channel in this mode: never print() here.
        mcp.run()
    else:
        asyncio.run(drive())


if __name__ == "__main__":
    main()
