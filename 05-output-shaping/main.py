"""Module 05: Output shaping. A cap, a notice, and tables an LLM can read.

Run: python 05-output-shaping/main.py
"""

from __future__ import annotations

import csv
import io
import json
import time
from dataclasses import dataclass
from decimal import Decimal
from typing import Any

import duckdb

MAX_CELL = 200


@dataclass
class Result:
    columns: list[str]
    rows: list[tuple[Any, ...]]
    truncated: bool


def run_capped(con: duckdb.DuckDBPyConnection, sql: str, cap: int) -> Result:
    """Execute and fetch at most cap rows, without computing the rest.

    Asking for cap + 1 rows is the trick: if the extra row exists we know the result was
    cut, and we never needed a COUNT(*) over the whole thing to find out.
    """
    cur = con.cursor()
    try:
        cur.execute(sql)
        columns = [d[0] for d in cur.description]
        rows = cur.fetchmany(cap + 1)
    finally:
        cur.close()
    return Result(columns, [tuple(r) for r in rows[:cap]], truncated=len(rows) > cap)


def cell(value: Any) -> str:
    """One value as text. NULL stays visible; huge values are cut."""
    if value is None:
        return "NULL"
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, Decimal):
        return format(value, "f")
    if isinstance(value, (bytes, bytearray)):
        return "0x" + bytes(value[:16]).hex() + ("..." if len(value) > 16 else "")
    text = str(value)
    if len(text) > MAX_CELL:
        return text[:MAX_CELL] + f"... [{len(text) - MAX_CELL} more chars]"
    return text


def markdown(res: Result) -> str:
    def esc(t: str) -> str:
        return t.replace("|", "\\|").replace("\r", " ").replace("\n", " ")

    lines = ["| " + " | ".join(esc(c) for c in res.columns) + " |",
             "| " + " | ".join("---" for _ in res.columns) + " |"]
    lines += ["| " + " | ".join(esc(cell(v)) for v in row) + " |" for row in res.rows]
    return "\n".join(lines)


def to_csv(res: Result) -> str:
    buf = io.StringIO()
    w = csv.writer(buf, lineterminator="\n")
    w.writerow(res.columns)
    for row in res.rows:
        w.writerow(["" if v is None else cell(v) for v in row])
    return buf.getvalue().rstrip("\n")


def to_json(res: Result, cap: int) -> str:
    """JSON must stay valid JSON, so the truncation notice lives inside the object."""
    payload: dict[str, Any] = {"row_count": len(res.rows), "truncated": res.truncated}
    if res.truncated:
        payload["row_cap"] = cap
    payload["rows"] = [dict(zip(res.columns, r)) for r in res.rows]
    return json.dumps(payload, default=str, ensure_ascii=False)


def render(res: Result, fmt: str, cap: int) -> str:
    if fmt == "json":
        return to_json(res, cap)
    if fmt not in ("markdown", "csv"):
        raise ValueError(f"format must be markdown, csv or json (got {fmt!r})")
    body = markdown(res) if fmt == "markdown" else to_csv(res)
    n = len(res.rows)
    if res.truncated:
        notice = (f"TRUNCATED: showing the first {n} rows; the query returned more (row cap {cap}). "
                  "Add WHERE/LIMIT, aggregate with GROUP BY, or select fewer columns.")
    else:
        notice = f"{n} row{'s' if n != 1 else ''}, {len(res.columns)} column{'s' if len(res.columns) != 1 else ''}."
    return body + ("\n# " if fmt == "csv" else "\n\n") + notice


def demo() -> None:
    con = duckdb.connect(":memory:")

    # 1. The cap, at its boundaries. Exactly cap rows is NOT truncated; cap + 1 is.
    assert run_capped(con, "SELECT * FROM range(5)", 5).truncated is False
    assert run_capped(con, "SELECT * FROM range(6)", 5).truncated is True
    assert len(run_capped(con, "SELECT * FROM range(6)", 5).rows) == 5

    # 2. It streams: a million-row, then a billion-row, result costs the same.
    for n in (1_000_000, 1_000_000_000):
        start = time.monotonic()
        res = run_capped(con, f"SELECT i, i % 7 AS bucket FROM range({n}) t(i)", 1000)
        took = time.monotonic() - start
        print(f"{n:>13,} row result capped to {len(res.rows)} rows in {took * 1000:.0f} ms")
        assert len(res.rows) == 1000 and res.truncated and took < 3

    # 3. Markdown: compact, and pipes and newlines cannot break the table.
    res = run_capped(con, "SELECT 1 AS id, 'a|b' AS txt, NULL AS missing, 'l1' || chr(10) || 'l2' AS two_lines", 10)
    md = render(res, "markdown", 10)
    print(md)
    assert "a\\|b" in md and "NULL" in md and "l1 l2" in md
    assert md.splitlines()[0] == "| id | txt | missing | two_lines |"
    assert md.endswith("1 row, 4 columns.")

    # 4. Huge cells are shortened so one blob cannot eat the context window.
    res = run_capped(con, "SELECT repeat('x', 100000) AS blob", 10)
    out = render(res, "markdown", 10)
    assert "99800 more chars" in out and len(out) < 400

    # 5. The truncation notice tells the agent what to do, in every format.
    res = run_capped(con, "SELECT * FROM range(100) t(n)", 3)
    assert "TRUNCATED: showing the first 3 rows" in render(res, "markdown", 3)
    assert render(res, "csv", 3).splitlines()[-1].startswith("# TRUNCATED")
    parsed = json.loads(render(res, "json", 3))
    assert parsed == {"row_count": 3, "truncated": True, "row_cap": 3, "rows": [{"n": 0}, {"n": 1}, {"n": 2}]}

    # 6. CSV and JSON are the compact options for big results. Compare sizes.
    res = run_capped(con, "SELECT i AS id, 'user_' || i AS name, i * 0.5 AS score FROM range(200) t(i)", 200)
    sizes = {f: len(render(res, f, 200)) for f in ("markdown", "csv", "json")}
    print("characters for the same 200 rows:", sizes)
    assert sizes["csv"] < sizes["markdown"] < sizes["json"]

    # 7. Dates, decimals and bytes become text; booleans stay readable.
    res = run_capped(con, "SELECT DATE '2026-01-02' AS d, 1.50::DECIMAL(5,2) AS m, TRUE AS b, 'abc'::BLOB AS raw", 1)
    assert render(res, "markdown", 1).splitlines()[2] == "| 2026-01-02 | 1.50 | true | 0x616263 |"
    try:
        render(res, "xml", 1)
    except ValueError as e:
        print("error:", e)
    print("OK")


if __name__ == "__main__":
    demo()
