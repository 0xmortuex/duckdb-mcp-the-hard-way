# Break It: The MCP Tool Wrapper

## Challenge 1: One print()

Add `print("starting")` at the top of `main()` when `--serve` is set, and run the demo.
What happens, and where do you see it?

**Hint:** The client reads your stdout as JSON-RPC, so `starting` is a malformed message
and the handshake fails or hangs. Anything that is for humans goes to `sys.stderr`.

## Challenge 2: Catch Exception

Change the decorator to `except Exception as e: raise ToolError(str(e))`. Add a bug to
`query` (say, call a method that does not exist) and run the demo. What does the agent see
now, and what is lost?

**Hint:** The agent sees `'NoneType' object has no attribute ...`, a message about *your*
bug, which it will try to "fix" by rewriting its SQL. You also lose the traceback. Convert
the failures that are the caller's fault, and let the rest be loud.

## Challenge 3: A tool with no docstring

Delete the docstring of `list_files` and look at `tools["list_files"].description`. Now
delete the type hint from `query(sql)`. What does the schema say?

**Hint:** An empty description means the model chooses by name alone, and it will guess how
file names work. Without a type hint the schema loses its `type`, so the model may send a
non-string.

## Challenge 4: Return a Python object

Make `list_files` return a `list[str]` instead of `str`. What does the client's
`content[0].text` look like? Which is better for an LLM, and why does the real server
return text?

**Hint:** The SDK serialises it for you, usually as JSON. For a model, a plain
newline-separated list or a markdown table is cheaper and clearer than quoting and
brackets. Choose the format for the reader, not the programmer.

→ [Next: Module 05](../05-output-shaping/README.md)
