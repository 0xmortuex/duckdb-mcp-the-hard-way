"""Module 01: DuckDB basics. An in-memory database that treats files as tables.

Run: python 01-duckdb-basics/main.py
Every claim in the README is asserted below, so a wrong claim fails the run.
"""

from __future__ import annotations

import os
import time

import duckdb

HERE = os.path.dirname(os.path.abspath(__file__))
ORDERS = os.path.join(HERE, "..", "data", "orders.csv").replace("\\", "/")


def demo() -> None:
    # 1. No server, no file: ":memory:" is a database that lives in this process.
    con = duckdb.connect(":memory:")
    assert con.execute("SELECT 6 * 7").fetchone() == (42,)

    # 2. A CSV file is a table once you wrap it in a table function.
    #    Types are detected from the data: no CREATE TABLE, no import step.
    by_country = con.execute(
        f"SELECT country, count(*) AS n FROM read_csv('{ORDERS}') GROUP BY country ORDER BY n DESC, country"
    ).fetchall()
    print("orders per country:", by_country)
    assert sum(n for _, n in by_country) == 40

    # 3. The shortcut: a quoted file name in FROM is read by extension.
    #    ("replacement scan": DuckDB sees a table name that is not a table.)
    assert con.execute(f"SELECT count(*) FROM '{ORDERS}'").fetchone() == (40,)

    # 4. DESCRIBE and SUMMARIZE are queries too. They give the agent a schema
    #    and a profile with no extra code.
    schema = con.execute(f"DESCRIBE SELECT * FROM '{ORDERS}'").fetchall()
    print("schema:", [(r[0], r[1]) for r in schema])
    assert [(r[0], r[1]) for r in schema][:2] == [("order_id", "BIGINT"), ("customer", "VARCHAR")]
    assert dict((r[0], r[1]) for r in schema)["placed_at"] == "DATE"

    summary = con.execute(f"SUMMARIZE '{ORDERS}'").fetchall()
    cols = [d[0] for d in con.description]
    amount = dict(zip(cols, next(r for r in summary if r[0] == "amount")))
    print("amount nulls:", amount["null_percentage"], "min:", amount["min"], "max:", amount["max"])
    assert float(amount["null_percentage"]) == 2.5  # one blank amount out of 40

    # 5. Streaming. execute() starts the query; fetchmany() pulls rows on demand.
    #    Asking for 11 rows of a 50-million-row result must not compute all of them.
    cur = con.cursor()
    start = time.monotonic()
    cur.execute("SELECT i, i * 2 AS twice FROM range(50000000) t(i)")
    first = cur.fetchmany(11)
    elapsed = time.monotonic() - start
    cur.close()
    print(f"first 11 of 50,000,000 rows in {elapsed * 1000:.0f} ms")
    assert len(first) == 11 and first[10] == (10, 20)
    assert elapsed < 5

    # 6. fetchall() is the opposite: it would build 50 million Python tuples.
    #    The whole server is built around never calling it on user queries.
    print("OK")


if __name__ == "__main__":
    demo()
