# Module 05: Output Shaping

## The Concept

The model reads whatever you return, and it pays for every character in its context
window. A result can fail the reader in three ways: too many rows, a single cell that is
enormous, or a format that spends half its characters on punctuation. This module fixes
all three, and adds the one thing most tools forget: telling the reader *that something was
left out*.

## The Row Cap That Streams

```python
rows = cur.fetchmany(cap + 1)
truncated = len(rows) > cap
rows = rows[:cap]
```

Fetching one row more than the cap answers "was it cut?" without computing the rest. A
separate `SELECT count(*)` would have to scan the whole file just to produce a number the
agent did not ask for.

Two edge cases are asserted in `main.py` because off-by-one errors live here: a result of
*exactly* `cap` rows is **not** truncated, and `cap + 1` rows is. Then the proof that it
streams: the same capped call over 1,000,000 and 1,000,000,000 rows takes about the same
fraction of a second (on this machine `0 ms` rounded). The engine stops producing rows when
you stop asking.

## The Notice

```
TRUNCATED: showing the first 1000 rows; the query returned more (row cap 1000).
Add WHERE/LIMIT, aggregate with GROUP BY, or select fewer columns.
```

Without the notice, the model sees 1,000 rows and reasonably concludes that is the whole
table, then reports an average over a truncated sample as if it were exact. The notice makes
the cut impossible to miss, and its second sentence says what to do about it. When nothing
was cut, the footer is a plain `5 rows, 3 columns.`, which also lets the model confirm a
count without counting table lines.

## Cells

`cell()` turns one value into text:

- `None` becomes `NULL`, visible, never an empty string that looks like missing output.
- Values over 200 characters are cut with `... [99800 more chars]`: one JSON blob or
  document column cannot swallow the context window, and the note says how much was lost.
- `BLOB` shows its first 16 bytes in hex; `Decimal` prints without scientific notation.

## Three Formats

| Format | Best for | Cost |
|--------|----------|------|
| `markdown` (default) | Reading, small and medium results | the `\| --- \|` rows and padding |
| `csv` | Large results; the model is good at CSV | no alignment, notice as a `# comment` line |
| `json` | When the model will pass the data to another tool | keys repeated on every row |

`main.py` prints the size of the same 200 rows in each: roughly CSV 3.4k, markdown 5.0k,
JSON 9.8k characters. So the default is readable and `format="csv"` is a real saving.

Details that bite:

- **Markdown escapes.** A value containing `|` or a newline would break the table. `esc()`
  turns `|` into `\|` and newlines into spaces.
- **JSON stays valid JSON.** Appending a text notice would make it unparseable, so the
  notice lives inside the object: `{"row_count": 3, "truncated": true, "row_cap": 3, "rows": [...]}`.
- **CSV gets the notice as the last line, prefixed with `#`**, which most CSV readers
  treat as a comment and a model reads as a note.
- An unknown format raises `ValueError("format must be markdown, csv or json ...")`: an
  instruction, not a crash.

## Run It

```bash
python 05-output-shaping/main.py
```

→ [Next: Module 06, Sandboxing](../06-sandboxing/README.md)
