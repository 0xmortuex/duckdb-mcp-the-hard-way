"""Module 07: Testing it for real. Real files, real escapes, a million rows, a live stdio server.

This module does not add features. It tests the server you built in Module 06 (it loads
06-sandboxing/main.py by path) and then tests the tests: a deliberately leaky sandbox must
make the escape suite fail.

Run: python 07-testing-it-for-real/main.py
"""

from __future__ import annotations

import asyncio
import importlib.util
import os
import sys
import tempfile
import time
from pathlib import Path
from types import ModuleType

import duckdb
from mcp import ClientSession
from mcp.client.stdio import StdioServerParameters, stdio_client

HERE = os.path.dirname(os.path.abspath(__file__))
SERVER_PY = os.path.join(HERE, "..", "06-sandboxing", "main.py")


def load_server() -> ModuleType:
    spec = importlib.util.spec_from_file_location("server06", SERVER_PY)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    sys.modules["server06"] = mod  # dataclasses look the module up by name
    spec.loader.exec_module(mod)
    return mod


# ---- 1. the escape suite: every attempt must be refused -----------------------------------


def make_world(root: Path) -> dict[str, str]:
    for d in ("data", "data2", "outside"):
        (root / d).mkdir()
    (root / "data" / "ok.csv").write_text("x\n1\n2\n", encoding="utf-8")
    (root / "data2" / "neighbour.csv").write_text("secret\nneighbour\n", encoding="utf-8")
    (root / "outside" / "secret.csv").write_text("secret\ntop-secret\n", encoding="utf-8")
    return {"data": str(root / "data"), "base": (root / "data").as_posix(),
            "secret": (root / "outside" / "secret.csv").as_posix(),
            "neighbour": (root / "data2" / "neighbour.csv").as_posix(),
            "outside_dir": (root / "outside").as_posix()}


def escape_attempts(w: dict[str, str]) -> dict[str, str]:
    """name -> SQL. Each one tries to read something it must not, or write anything."""
    system = "C:/Windows/win.ini" if sys.platform == "win32" else "/etc/passwd"
    return {
        "absolute path elsewhere": f"SELECT * FROM read_csv('{w['secret']}')",
        "bare quoted path elsewhere": f"SELECT * FROM '{w['secret']}'",
        "system file": f"SELECT * FROM read_text('{system}')",
        "relative traversal": "SELECT * FROM '../outside/secret.csv'",
        "absolute traversal": f"SELECT * FROM read_csv('{w['base']}/../outside/secret.csv')",
        "same-prefix sibling folder": f"SELECT * FROM read_csv('{w['neighbour']}')",
        "glob outside": f"SELECT * FROM glob('{w['outside_dir']}/*')",
        "url": "SELECT * FROM read_csv('https://example.com/x.csv')",
        "copy out": f"COPY (SELECT 1) TO '{w['base']}/dropped.csv'",
        "explain analyze copy": f"EXPLAIN ANALYZE COPY (SELECT 1) TO '{w['base']}/dropped.csv'",
        "install": "INSTALL httpfs",
        "attach": "ATTACH ':memory:' AS m",
        "two statements": "SELECT 1; SELECT 2",
    }


def run_escape_suite(sb: object, w: dict[str, str]) -> list[str]:
    """Return the names of attempts that were NOT refused (the failures)."""
    leaks = []
    for name, sql in escape_attempts(w).items():
        try:
            sb.run(sql)  # type: ignore[attr-defined]
        except Exception as e:  # noqa: BLE001 - any refusal counts; the type is checked below
            if type(e).__name__ != "SandboxError":
                leaks.append(f"{name} (wrong error type {type(e).__name__})")
        else:
            leaks.append(name)
    if os.path.exists(w["base"] + "/dropped.csv"):
        leaks.append("a file was written")
    return leaks


def test_escapes(mod: ModuleType) -> None:
    with tempfile.TemporaryDirectory() as tmp:
        w = make_world(Path(tmp))
        leaks = run_escape_suite(mod.Sandbox(w["data"]), w)
        assert leaks == [], f"escapes that worked: {leaks}"
    print("escape suite: 13 attempts, all refused")


# ---- 2. test the tests: a sandbox with the safety removed must FAIL the suite -------------


def test_the_tests(mod: ModuleType) -> None:
    class Leaky(mod.Sandbox):  # type: ignore[misc, name-defined]
        """Same gate and same API, but DuckDB's sandbox settings were 'forgotten'."""

        def __init__(self, folder: str) -> None:
            self.folder = folder.replace("\\", "/")
            self.max_rows, self.timeout = 1000, 30.0
            self.con = duckdb.connect(":memory:")

    with tempfile.TemporaryDirectory() as tmp:
        w = make_world(Path(tmp))
        leaks = run_escape_suite(Leaky(w["data"]), w)
    print("leaky sandbox leaks:", leaks)
    # DuckDB's folder rule is what stops these; without it they all read real data.
    for name in ("absolute path elsewhere", "absolute traversal", "same-prefix sibling folder", "glob outside"):
        assert name in leaks, f"the suite failed to notice that {name!r} leaks"
    # Relative traversal is also stopped by our own path check (a second layer).
    assert "relative traversal" not in leaks
    # The gate is a separate layer, so writes are still caught even with the sandbox gone.
    assert "copy out" not in leaks and "attach" not in leaks
    print("tests tested: removing the sandbox is detected")


# ---- 3. a big file -------------------------------------------------------------------------


def test_big_files(mod: ModuleType) -> None:
    with tempfile.TemporaryDirectory() as tmp:
        tmp = tmp.replace("\\", "/")
        gen = duckdb.connect()
        src = "SELECT i AS id, 'user_' || (i % 1000) AS name, i % 7 AS bucket FROM range(1000000) t(i)"
        t0 = time.monotonic()
        gen.execute(f"COPY ({src}) TO '{tmp}/big.parquet' (FORMAT parquet)")
        gen.execute(f"COPY ({src}) TO '{tmp}/big.csv' (FORMAT csv, HEADER)")
        print(f"generated 2 files of 1,000,000 rows in {time.monotonic() - t0:.1f}s")
        sb = mod.Sandbox(tmp, max_rows=1000, timeout=60)
        for name in ("big.csv", "big.parquet"):
            t0 = time.monotonic()
            res = sb.run(f"SELECT * FROM '{name}'")
            took = time.monotonic() - t0
            assert len(res.rows) == 1000 and res.truncated
            assert took < 5, f"{name}: {took:.1f}s means it is not streaming"
            agg = sb.run(f"SELECT count(*), max(id) FROM '{name}'")
            assert agg.rows == [(1_000_000, 999_999)]
            print(f"{name}: SELECT * capped at 1000 rows in {took * 1000:.0f} ms; count(*) = 1,000,000")


# ---- 4. the handshake: launch the real server as a subprocess ---------------------------------


async def test_stdio() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        (Path(tmp) / "t.csv").write_text("id,name\n1,Ada\n2,Grace\n", encoding="utf-8")
        params = StdioServerParameters(
            command=sys.executable, args=[SERVER_PY, "--serve", "--dir", tmp]
        )
        async with stdio_client(params) as (read, write), ClientSession(read, write) as s:
            init = await s.initialize()
            assert init.server_info.name == "duckdb-tutorial"
            tools = (await s.list_tools()).tools
            assert {t.name for t in tools} == {"list_files", "describe_file", "query"}
            assert all(t.description for t in tools)

            res = await s.call_tool("list_files", {})
            assert res.content[0].text.strip() == "t.csv"  # type: ignore[union-attr]
            res = await s.call_tool("query", {"sql": "SELECT count(*) AS n FROM 't.csv'"})
            assert "| 2 |" in res.content[0].text  # type: ignore[union-attr]

            # errors are tool results with is_error set, and the text survives the trip
            res = await s.call_tool("query", {"sql": "DROP TABLE t"})
            assert res.is_error and "read-only" in res.content[0].text  # type: ignore[union-attr]
            res = await s.call_tool("query", {"sql": "SELECT * FROM read_csv('C:/Windows/win.ini')"})
            assert res.is_error and "File access is limited" in res.content[0].text  # type: ignore[union-attr]
    print("stdio handshake: tools listed, query ok, errors readable")


def main() -> None:
    mod = load_server()
    test_escapes(mod)
    test_the_tests(mod)
    test_big_files(mod)
    asyncio.run(test_stdio())
    print("OK")


if __name__ == "__main__":
    main()
