"""Module 03: Safe SQL gating. Let the parser decide what a statement is.

Run: python 03-safe-sql-gating/main.py
"""

from __future__ import annotations

import os
import re
import tempfile

import duckdb


class SqlRejected(Exception):
    """A statement the server refuses to run. The message is for the agent."""


def statement_types(con: duckdb.DuckDBPyConnection, sql: str) -> list[str]:
    """What DuckDB's own parser says each statement is. No string guessing."""
    try:
        return [s.type.name for s in con.extract_statements(sql)]
    except duckdb.Error as e:
        raise SqlRejected(f"SQL syntax error: {e}") from e


def naive_gate(con: duckdb.DuckDBPyConnection, sql: str) -> None:
    """The first idea: allow SELECT and EXPLAIN. It has a hole (see demo step 4)."""
    kinds = statement_types(con, sql)
    if len(kinds) != 1 or kinds[0] not in ("SELECT", "EXPLAIN"):
        raise SqlRejected(f"{kinds} is not allowed")


EXPLAIN_PREFIX = re.compile(r"^\s*explain(?:\s+analyze\b)?(?:\s*\([^)]*\))?\s*", re.IGNORECASE)


def check_sql(con: duckdb.DuckDBPyConnection, sql: str) -> None:
    """Allow exactly one read-only statement, or raise SqlRejected."""
    if not sql.strip():
        raise SqlRejected("The SQL is empty.")
    kinds = statement_types(con, sql)
    if len(kinds) != 1:
        raise SqlRejected(f"Send exactly one SQL statement per call (got {len(kinds)}).")
    if kinds[0] == "EXPLAIN":
        # EXPLAIN ANALYZE executes what follows, so judge what follows.
        inner = statement_types(con, EXPLAIN_PREFIX.sub("", sql, count=1))
        if inner != ["SELECT"]:
            raise SqlRejected("EXPLAIN is only allowed on a SELECT query.")
        return
    if kinds[0] != "SELECT":
        raise SqlRejected(
            f"{kinds[0]} statements are blocked: this server is read-only. Allowed: "
            "SELECT / WITH / VALUES / FROM, DESCRIBE, SUMMARIZE, SHOW and EXPLAIN."
        )


def demo() -> None:
    con = duckdb.connect(":memory:")

    # 1. DuckDB classifies statements for us. Note what counts as a SELECT.
    cases = {
        "SELECT 1": "SELECT",
        "WITH t AS (SELECT 1 AS x) SELECT x FROM t": "SELECT",
        "FROM range(3)": "SELECT",
        "VALUES (1), (2)": "SELECT",
        "DESCRIBE SELECT 1": "SELECT",
        "SUMMARIZE SELECT 1": "SELECT",
        "SHOW TABLES": "SELECT",
        "EXPLAIN SELECT 1": "EXPLAIN",
        "CREATE TABLE t(a INT)": "CREATE",
        "INSERT INTO t VALUES (1)": "INSERT",
        "COPY (SELECT 1) TO 'x.csv'": "COPY",
        "ATTACH ':memory:' AS m": "ATTACH",
        "INSTALL httpfs": "LOAD",
        "LOAD httpfs": "LOAD",
        "SET threads = 1": "SET",
        "PRAGMA version": "PRAGMA",
        "CALL pragma_version()": "CALL",
        "EXPORT DATABASE 'd'": "EXPORT",
    }
    for sql, kind in cases.items():
        assert statement_types(con, sql) == [kind], (sql, statement_types(con, sql))
    print(f"{len(cases)} statements classified by DuckDB's parser")

    # 2. A comment or odd casing cannot fool a parser. It could fool startswith("select").
    assert statement_types(con, "/* select */ DrOp TABLE t") == ["DROP"]
    assert statement_types(con, "  \n  select 1  ") == ["SELECT"]
    # Two statements in one string are two statements, whatever the first one says.
    assert statement_types(con, "SELECT 1; DROP TABLE t") == ["SELECT", "DROP"]

    # 3. Why gating is needed at all: DuckDB will happily WRITE files.
    with tempfile.TemporaryDirectory() as tmp:
        tmp = tmp.replace("\\", "/")
        con.execute(f"COPY (SELECT 1 AS x) TO '{tmp}/written.csv'")
        assert os.path.exists(tmp + "/written.csv")
        print("ungated connection wrote", tmp + "/written.csv")

        # 4. The hole in a naive gate. EXPLAIN ANALYZE really executes its statement.
        target = tmp + "/pwned.csv"
        sql = f"EXPLAIN ANALYZE COPY (SELECT 1 AS x) TO '{target}'"
        assert statement_types(con, sql) == ["EXPLAIN"]
        naive_gate(con, sql)  # passes!
        con.execute(sql)
        assert os.path.exists(target), "naive gate let a write through"
        os.remove(target)
        print("naive gate: EXPLAIN ANALYZE COPY wrote a file")

        # 5. The real gate judges the statement inside EXPLAIN.
        for bad in (sql, f"explain (analyze) copy (select 1) to '{target}'"):
            try:
                check_sql(con, bad)
            except SqlRejected as e:
                print("rejected:", e)
            else:
                raise AssertionError("gate accepted a write")
        assert not os.path.exists(target)

    # 6. And everything else the server must refuse, with messages that say what to do.
    for sql in ("CREATE TABLE t(a INT)", "INSERT INTO t VALUES (1)", "DROP TABLE t",
                "COPY (SELECT 1) TO 'x.csv'", "ATTACH ':memory:' AS m", "INSTALL httpfs",
                "SET threads = 1", "PRAGMA version", "SELECT 1; SELECT 2", "", "SELEC 1"):
        try:
            check_sql(con, sql)
        except SqlRejected:
            continue
        raise AssertionError(f"{sql!r} was accepted")
    for sql in ("SELECT 1", "WITH t AS (SELECT 1) SELECT * FROM t", "DESCRIBE SELECT 1",
                "SUMMARIZE SELECT 1", "EXPLAIN SELECT 1", "EXPLAIN ANALYZE SELECT 1", "FROM range(2)"):
        check_sql(con, sql)
    print("OK")


if __name__ == "__main__":
    demo()
