# Break It: Reading Files

## Challenge 1: Skip the quote escaping

Replace `sql_literal` with `"'" + text + "'"` and run `main.py`. Which step fails, and how?

**Hint:** The `o'brien.csv` step. The path ends the string at the apostrophe. Imagine a
file named `x'); DROP TABLE t; --.csv`. Here the gate in Module 03 would still stop it,
but never rely on a second layer to excuse sloppy quoting in the first.

## Challenge 2: Rewrite literals that are not files

Remove the `os.path.isfile(candidate)` check from `rewrite_paths`, so every literal that
ends in `.csv` is rewritten. Run step 4. What breaks, and what does the agent see when it
mistypes a file name?

**Hint:** `'ghost.csv'` becomes an absolute path that does not exist, and the agent sees
a long machine-specific path in the error instead of the name it typed. The existence
check keeps errors in the agent's own vocabulary.

## Challenge 3: A name that exists in two folders

Create `a/people.csv` and `b/people.csv` and allow both folders. What does `rewrite_paths`
do if you simply take the first match? What should it do?

**Hint:** Silently picking one is the worst answer: the agent gets plausible data from the
wrong file. The real server finds every match and, when there is more than one, raises
"exists in more than one allowed folder ... Use the full path."

## Challenge 4: Add Excel

Try `SELECT * FROM read_xlsx('book.xlsx')` in a plain connection. What does DuckDB say?
Why does the real server not support `.xlsx`?

**Hint:** Reading Excel is an *extension* that DuckDB downloads on first use. Module 06 turns
extension install and load off on purpose, so Excel and the sandbox are in direct tension.
Exporting the sheet to CSV is the safe path.

→ [Next: Module 03](../03-safe-sql-gating/README.md)
