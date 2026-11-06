# Break It: Output Shaping

## Challenge 1: Hide the truncation

Remove the notice from `render` (return only the table). Ask yourself what an agent would
conclude from `SELECT * FROM range(100000)` capped at 1,000 rows, then from
`SELECT avg(n) FROM (SELECT * FROM big LIMIT 1000)`. Which answer is silently wrong?

**Hint:** Neither query *errors*, and both look complete. A tool that can drop data must
say so every time, in words the model acts on.

## Challenge 2: Count first

Replace `fetchmany(cap + 1)` with a `SELECT count(*)` over the query followed by a `LIMIT`.
Time it on `range(1000000000)`. Then on a real 1,000,000-row CSV.

**Hint:** The count must evaluate the whole query, so the cost scales with the data, which
is the cost the cap was supposed to avoid. For a CSV it re-reads the file.

## Challenge 3: A pipe in the data

Change the `esc` function to do nothing. Query `SELECT 'a|b' AS txt, 'x' AS other`. How many
columns does the markdown table appear to have?

**Hint:** Three: the `|` splits the cell. Anything that can contain user data must be
escaped on the way into a text format. Do the same experiment with a CSV value containing a
comma (the `csv` module quotes it for you; hand-joined strings would not).

## Challenge 4: Make a cell cap in characters wrong

The cell limit counts characters, not bytes or tokens. Find a string of 200 characters
whose token count is much larger than one of 200 ordinary English letters.

**Hint:** Non-Latin text, emoji and random hex tokenise poorly, so 200 characters may be
100+ tokens. A cap is a blunt instrument. The row cap and cell cap together bound the
worst case (rows x columns x 200), which is the property you actually need.

→ [Next: Module 06](../06-sandboxing/README.md)
