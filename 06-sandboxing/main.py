"""Module 06: Sandboxing. The finished minimal server: gated, capped, and confined.

Run: python 06-sandboxing/main.py                    (attacks it, in-process and over stdio)
     python 06-sandboxing/main.py --serve --dir DATA  (just the server)
"""

from __future__ import annotations

import argparse
import asyncio
import functools
import os
import re
import sys
import tempfile
import threading
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any, TypeVar

import duckdb
from mcp import ClientSession
from mcp.client.stdio import StdioServerParameters, stdio_client
from mcp.server.mcpserver import MCPServer
from mcp.server.mcpserver.exceptions import ToolError

HERE = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(HERE, "..", "data")
SUFFIXES = (".csv", ".tsv", ".parquet", ".json", ".ndjson", ".jsonl")
QUOTED = re.compile(r"'((?:[^']|'')*)'")
EXPLAIN_PREFIX = re.compile(r"^\s*explain(?:\s+analyze\b)?(?:\s*\([^)]*\))?\s*", re.IGNORECASE)


class SandboxError(Exception):
    """An expected failure; the message is written for the agent."""


@dataclass
class Result:
    columns: list[str]
    rows: list[tuple[Any, ...]]
    truncated: bool


class Sandbox:
    def __init__(self, folder: str, max_rows: int = 1000, timeout: float = 30.0) -> None:
        if not os.path.isdir(folder):
            raise SandboxError(f"allowed folder {folder!r} does not exist")
        self.folder = Path(folder).resolve().as_posix().rstrip("/")
        self.max_rows, self.timeout = max_rows, timeout
        self._spill = tempfile.TemporaryDirectory(prefix="duckdb-tutorial-")
        con = duckdb.connect(":memory:")
        con.execute("SET temp_directory = ?", [self._spill.name])
        con.execute("SET autoinstall_known_extensions = false")
        con.execute("SET autoload_known_extensions = false")
        # (1) Say where files may be read. The trailing slash makes it a folder, not a name prefix.
        con.execute("SET allowed_directories = ?", [[self.folder + "/"]])
        # (2) Turn everything else off: other paths, URLs, INSTALL/LOAD. Must come AFTER (1):
        #     DuckDB refuses to change allowed_directories once access is disabled.
        con.execute("SET enable_external_access = false")
        # (3) Freeze the settings so no SQL can flip them back.
        con.execute("SET lock_configuration = true")
        self.con = con

    # -- statement gate (Module 03) --
    def check(self, sql: str) -> None:
        try:
            kinds = [s.type.name for s in self.con.extract_statements(sql)]
        except duckdb.Error as e:
            raise SandboxError(f"SQL syntax error: {e}") from e
        if len(kinds) != 1:
            raise SandboxError(f"Send exactly one SQL statement per call (got {len(kinds)}).")
        if kinds[0] == "EXPLAIN":
            inner = [s.type.name for s in self.con.extract_statements(EXPLAIN_PREFIX.sub("", sql, count=1))]
            if inner != ["SELECT"]:
                raise SandboxError("EXPLAIN is only allowed on a SELECT query.")
        elif kinds[0] != "SELECT":
            raise SandboxError(f"{kinds[0]} statements are blocked: this server is read-only.")

    # -- friendly names (Module 02) --
    def absolutise(self, sql: str) -> str:
        def repl(m: re.Match[str]) -> str:
            text = m.group(1).replace("''", "'")
            full = os.path.normpath(os.path.join(self.folder, text))
            inside = Path(full).resolve().as_posix().startswith(self.folder + "/")
            if text.lower().endswith(SUFFIXES) and not os.path.isabs(text) and inside and os.path.isfile(full):
                return "'" + full.replace("\\", "/").replace("'", "''") + "'"
            return m.group(0)

        return QUOTED.sub(repl, sql)

    # -- run with a cap (Module 05) and a time limit --
    def run(self, sql: str) -> Result:
        sql = self.absolutise(sql)
        self.check(sql)
        cur = self.con.cursor()
        timed_out = threading.Event()

        def stop() -> None:
            timed_out.set()
            cur.interrupt()

        timer = threading.Timer(self.timeout, stop)
        timer.start()
        try:
            cur.execute(sql)
            cols = [d[0] for d in cur.description]
            rows = cur.fetchmany(self.max_rows + 1)
        except duckdb.Error as e:
            if timed_out.is_set():
                raise SandboxError(f"Query stopped after the {self.timeout:g}s time limit.") from e
            msg = str(e)
            if "file system operations are disabled" in msg:
                msg += f"\nFile access is limited to {self.folder}. Call list_files."
            raise SandboxError(msg) from e
        finally:
            timer.cancel()
            cur.close()
        return Result(cols, [tuple(r) for r in rows[: self.max_rows]], len(rows) > self.max_rows)


# ---- the MCP server ---------------------------------------------------------------------

mcp = MCPServer(
    "duckdb-tutorial",
    instructions="Query data files with read-only SQL. Call list_files first, then query.",
)
BOX: Sandbox | None = None
F = TypeVar("F", bound=Callable[..., Any])


def tool(fn: F) -> F:
    @functools.wraps(fn)
    def wrapper(*args: Any, **kwargs: Any) -> Any:
        try:
            return fn(*args, **kwargs)
        except SandboxError as e:
            raise ToolError(str(e)) from e

    mcp.tool()(wrapper)
    return fn


def box() -> Sandbox:
    if BOX is None:
        raise SandboxError("server not configured")
    return BOX


def table(res: Result) -> str:
    esc = lambda v: ("NULL" if v is None else str(v)).replace("|", "\\|").replace("\n", " ")  # noqa: E731
    lines = ["| " + " | ".join(res.columns) + " |", "| " + " | ".join("---" for _ in res.columns) + " |"]
    lines += ["| " + " | ".join(esc(v) for v in r) + " |" for r in res.rows]
    if res.truncated:
        lines += ["", f"TRUNCATED: showing the first {len(res.rows)} rows. Add WHERE/LIMIT or aggregate."]
    return "\n".join(lines)


@tool
def list_files() -> str:
    """List the data files you can query. Call this first; use the names directly in SQL."""
    names = []
    for dirpath, _dirs, files in os.walk(box().folder):
        for n in files:
            if n.lower().endswith(SUFFIXES):
                names.append(os.path.relpath(os.path.join(dirpath, n), box().folder).replace("\\", "/"))
    return "\n".join(sorted(names)) or "No data files found."


@tool
def describe_file(path: str) -> str:
    """Column names and types of one data file. Use it before writing a query."""
    return table(box().run(f"DESCRIBE SELECT * FROM '{path}'"))


@tool
def query(sql: str) -> str:
    """Run one read-only SQL statement over the data files, e.g. SELECT * FROM 'orders.csv'.

    Results stop at the row cap with a TRUNCATED notice; aggregate instead of fetching rows.
    """
    return table(box().run(sql))


# ---- attack it -------------------------------------------------------------------------


def attacks() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        for d in ("data", "data2", "outside"):
            (root / d).mkdir()
        (root / "data" / "ok.csv").write_text("x\n1\n2\n", encoding="utf-8")
        (root / "data2" / "neighbour.csv").write_text("secret\n1\n", encoding="utf-8")
        (root / "outside" / "secret.csv").write_text("secret\n1\n", encoding="utf-8")
        sb = Sandbox(str(root / "data"), max_rows=50, timeout=0.5)

        assert sb.run("SELECT sum(x) FROM 'ok.csv'").rows == [(3,)]

        def must_fail(sql: str, contains: str = "") -> None:
            try:
                sb.run(sql)
            except SandboxError as e:
                assert contains in str(e), (sql, str(e))
                return
            raise AssertionError(f"was allowed: {sql}")

        out = (root / "outside" / "secret.csv").as_posix()
        near = (root / "data2" / "neighbour.csv").as_posix()
        base = (root / "data").as_posix()
        windows = "C:/Windows/win.ini" if sys.platform == "win32" else "/etc/passwd"
        must_fail(f"SELECT * FROM read_csv('{out}')", "limited to")  # absolute path elsewhere
        must_fail(f"SELECT * FROM read_text('{windows}')", "limited to")  # the system file
        must_fail("SELECT * FROM '../outside/secret.csv'")  # relative traversal
        must_fail(f"SELECT * FROM read_csv('{base}/../outside/secret.csv')", "limited to")  # absolute traversal
        must_fail(f"SELECT * FROM read_csv('{near}')", "limited to")  # sibling with the same prefix
        must_fail(f"SELECT * FROM glob('{(root / 'outside').as_posix()}/*')", "limited to")
        must_fail("SELECT * FROM read_csv('https://example.com/x.csv')", "limited to")
        must_fail("INSTALL httpfs", "blocked")
        must_fail("ATTACH ':memory:' AS m", "blocked")
        must_fail("COPY (SELECT 1) TO 'x.csv'", "blocked")
        must_fail(f"EXPLAIN ANALYZE COPY (SELECT 1) TO '{base}/pwned.csv'", "EXPLAIN")
        assert not (root / "data" / "pwned.csv").exists() and not (root / "data" / "x.csv").exists()
        # Even bypassing the gate, DuckDB itself refuses to loosen its settings.
        for stmt in ("SET enable_external_access = true", "SET allowed_directories = []"):
            try:
                sb.con.execute(stmt)
            except duckdb.Error as e:
                assert "locked" in str(e)
            else:
                raise AssertionError(stmt)
        # Row cap and timeout.
        res = sb.run("SELECT * FROM range(1000000)")
        assert len(res.rows) == 50 and res.truncated
        must_fail("SELECT count(*) FROM range(100000000) a, range(100000000) b", "time limit")
        assert sb.run("SELECT 1").rows == [(1,)]  # still alive afterwards
    print("in-process attacks: all refused")


async def over_stdio() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        (Path(tmp) / "t.csv").write_text("id,name\n1,Ada\n2,Grace\n", encoding="utf-8")
        outside = Path(tmp).parent / "duckdb_tutorial_secret.csv"
        outside.write_text("pw\nhunter2\n", encoding="utf-8")
        try:
            params = StdioServerParameters(
                command=sys.executable, args=[os.path.abspath(__file__), "--serve", "--dir", tmp]
            )
            async with stdio_client(params) as (read, write), ClientSession(read, write) as s:
                await s.initialize()
                names = {t.name for t in (await s.list_tools()).tools}
                assert names == {"list_files", "describe_file", "query"}, names
                res = await s.call_tool("query", {"sql": "SELECT name FROM 't.csv' WHERE id = 2"})
                assert "Grace" in res.content[0].text  # type: ignore[union-attr]
                res = await s.call_tool("describe_file", {"path": "t.csv"})
                assert "| id | BIGINT" in res.content[0].text  # type: ignore[union-attr]
                res = await s.call_tool("query", {"sql": f"SELECT * FROM read_csv('{outside.as_posix()}')"})
                print("over stdio:", res.content[0].text.splitlines()[0][:90])  # type: ignore[union-attr]
                assert res.is_error and "hunter2" not in res.content[0].text  # type: ignore[union-attr]
        finally:
            outside.unlink()
    print("OK")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--serve", action="store_true")
    ap.add_argument("--dir", default=DATA)
    args = ap.parse_args()
    if args.serve:
        global BOX
        try:
            BOX = Sandbox(args.dir)
        except SandboxError as e:
            sys.exit(f"error: {e}")
        mcp.run()
    else:
        attacks()
        asyncio.run(over_stdio())


if __name__ == "__main__":
    main()
