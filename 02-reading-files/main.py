"""Module 02: Reading files. One reader per format, and friendly file names.

Run: python 02-reading-files/main.py
"""

from __future__ import annotations

import gzip
import os
import re
import tempfile

import duckdb

DATA_SUFFIXES = (".csv", ".tsv", ".parquet", ".json", ".ndjson", ".jsonl")
TEXT_SUFFIXES = (".csv", ".tsv", ".json", ".ndjson", ".jsonl")  # these may be .gz


def data_kind(name: str) -> str | None:
    """'csv' | 'tsv' | 'parquet' | 'json' for a data file name, else None."""
    low = name.lower()
    if low.endswith(".gz"):
        low = low[:-3]
        if not low.endswith(TEXT_SUFFIXES):
            return None
    for suffix, kind in ((".csv", "csv"), (".tsv", "tsv"), (".parquet", "parquet"),
                         (".json", "json"), (".ndjson", "json"), (".jsonl", "json")):
        if low.endswith(suffix):
            return kind
    return None


def sql_literal(text: str) -> str:
    """Quote text as a SQL string. A path with an apostrophe must not break out."""
    return "'" + text.replace("'", "''") + "'"


def reader_sql(path: str) -> str:
    """The table function for this file: read_csv('...'), read_parquet('...'), ..."""
    kind = data_kind(path)
    if kind == "parquet":
        return f"read_parquet({sql_literal(path)})"
    if kind == "json":
        return f"read_json_auto({sql_literal(path)})"  # handles arrays AND newline-delimited
    if kind in ("csv", "tsv"):
        return f"read_csv({sql_literal(path)})"  # sniffs the delimiter, so TSV needs nothing extra
    raise ValueError(f"{path!r} is not a supported data file ({', '.join(DATA_SUFFIXES)})")


def list_data_files(folder: str) -> list[str]:
    """Relative, forward-slash paths of every data file under folder."""
    found = []
    for dirpath, dirnames, filenames in os.walk(folder):
        dirnames[:] = sorted(d for d in dirnames if not d.startswith("."))
        for name in sorted(filenames):
            if data_kind(name):
                full = os.path.join(dirpath, name)
                found.append(os.path.relpath(full, folder).replace("\\", "/"))
    return sorted(found)


# A quoted literal: 'text' ('' escapes a quote) or "text".
QUOTED = re.compile(r"'((?:[^']|'')*)'|\"((?:[^\"]|\"\")*)\"")


def rewrite_paths(sql: str, folder: str) -> str:
    """Make 'orders.csv' work: replace a relative data-file literal by its absolute path,
    but only when that file really exists. Everything else is left untouched."""

    def repl(m: re.Match[str]) -> str:
        text = m.group(1).replace("''", "'") if m.group(1) is not None else m.group(2)
        if os.path.isabs(text) or data_kind(text) is None:
            return m.group(0)
        candidate = os.path.join(folder, text)
        if os.path.isfile(candidate):
            return sql_literal(os.path.abspath(candidate).replace("\\", "/"))
        return m.group(0)

    return QUOTED.sub(repl, sql)


def demo() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        tmp = tmp.replace("\\", "/")
        os.makedirs(tmp + "/archive")
        with open(tmp + "/people.csv", "w", encoding="utf-8") as f:
            f.write("id,name\n1,Ada\n2,Grace\n3,Linus\n")
        with open(tmp + "/people.tsv", "w", encoding="utf-8") as f:
            f.write("id\tname\n1\tAda\n2\tGrace\n")
        with open(tmp + "/events.ndjson", "w", encoding="utf-8") as f:
            f.write('{"id": 1, "kind": "view"}\n{"id": 2, "kind": "buy"}\n')
        with open(tmp + "/doc.json", "w", encoding="utf-8") as f:
            f.write('[{"id": 1}, {"id": 2}, {"id": 3}, {"id": 4}]')
        with gzip.open(tmp + "/archive/old.csv.gz", "wt", encoding="utf-8") as f:
            f.write("id,name\n9,Old\n")
        with open(tmp + "/notes.txt", "w", encoding="utf-8") as f:
            f.write("not data")
        con = duckdb.connect(":memory:")
        con.execute(f"COPY (SELECT * FROM range(100) t(n)) TO '{tmp}/numbers.parquet' (FORMAT parquet)")

        # 1. What is there? Only files we know how to read.
        files = list_data_files(tmp)
        print("files:", files)
        assert files == ["archive/old.csv.gz", "doc.json", "events.ndjson", "numbers.parquet",
                         "people.csv", "people.tsv"]

        # 2. Every format through its reader. The point: the caller never picks a reader.
        expected = {"people.csv": 3, "people.tsv": 2, "events.ndjson": 2, "doc.json": 4,
                    "numbers.parquet": 100, "archive/old.csv.gz": 1}
        for rel, count in expected.items():
            got = con.execute(f"SELECT count(*) FROM {reader_sql(tmp + '/' + rel)}").fetchone()
            assert got == (count,), (rel, got)
        # types come from the data: ids are numbers, not text
        types = dict((r[0], r[1]) for r in con.execute(f"DESCRIBE SELECT * FROM {reader_sql(tmp + '/people.tsv')}").fetchall())
        assert types == {"id": "BIGINT", "name": "VARCHAR"}

        # 3. Friendly names. The agent writes 'people.csv'; we make it absolute.
        sql = rewrite_paths("SELECT name FROM 'people.csv' WHERE id = 2", tmp)
        print("rewritten:", sql)
        assert tmp + "/people.csv" in sql
        assert con.execute(sql).fetchall() == [("Grace",)]
        sql = rewrite_paths("SELECT count(*) FROM read_csv('archive/old.csv.gz')", tmp)
        assert con.execute(sql).fetchone() == (1,)

        # 4. Literals that are not existing data files are left alone.
        same = "SELECT 'ghost.csv' AS a, 'hello' AS b, 'it''s.csv' AS c"
        assert rewrite_paths(same, tmp) == same

        # 5. A name with an apostrophe still works because of sql_literal.
        with open(tmp + "/o'brien.csv", "w", encoding="utf-8") as f:
            f.write("x\n1\n")
        quirky = tmp + "/o'brien.csv"
        assert con.execute(f"SELECT x FROM {reader_sql(quirky)}").fetchone() == (1,)

        # 6. Unsupported files fail with a message, not a crash deep in DuckDB.
        try:
            reader_sql(tmp + "/notes.txt")
        except ValueError as e:
            print("error:", e)
        else:
            raise AssertionError("expected ValueError")
    print("OK")


if __name__ == "__main__":
    demo()
