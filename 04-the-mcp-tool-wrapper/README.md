# Module 04: The MCP Tool Wrapper

> **Warning.** The server in this module is gated (read-only SQL) but **not sandboxed**. Its
> SQL can read any file on your disk, and the demo proves it in its last step. Module 06
> fixes that. Do not point a real agent at this one.

## The Concept

Everything so far is a Python library. An agent cannot import it. MCP is how it gets
called: the client launches your program, speaks JSON-RPC over its stdin and stdout, lists
the tools, and calls them. With the `mcp` package, a tool is a typed Python function:

```python
mcp = MCPServer("duckdb-tutorial", instructions="Query data files with SQL. Call list_files first.")

@mcp.tool()
def query(sql: str) -> str:
    """Run one read-only SQL statement ..."""
```

Two things are generated from that function, and both are the agent's only documentation:

- the **input schema**, from the type hints (`sql: str` becomes a required string; the
  demo asserts `input_schema["required"] == ["sql"]`);
- the **description**, from the docstring.

Write the docstring as instructions to a reader who cannot ask questions. "Call this first.
The paths it prints can be used directly in SQL" does more for tool selection than any
clever name.

## stdout Is the Wire

In `--serve` mode the client reads your stdout as protocol. One stray `print()` corrupts the
stream. Diagnostics go to stderr (the `mcp` package logs there). `main.py` therefore has two
modes: `--serve` (never prints) and the default demo, which launches *itself* as a
subprocess with `--serve` and talks to it with the real MCP client, exactly the way Claude
would:

```python
params = StdioServerParameters(command=sys.executable, args=[__file__, "--serve", "--dir", DATA])
async with stdio_client(params) as (read, write), ClientSession(read, write) as session:
    await session.initialize()
    tools = await session.list_tools()
    res = await session.call_tool("query", {"sql": "..."})
```

## Errors the Agent Can Actually See

This is the lesson of the module. When a tool function raises, what reaches the model?

| What you raise | What the agent sees |
|----------------|---------------------|
| `ToolError("DROP statements are blocked: this server is read-only.")` | `Error executing tool query: DROP statements are blocked: this server is read-only.` |
| `ValueError("this message never reaches the agent")` | `Error executing tool query_unwrapped` |

`MCPServer` forwards the message of a `ToolError` and *hides every other exception*, on the
reasonable grounds that a raw traceback can leak internals. The cost is that a perfectly
good error message is lost unless you convert it. The pattern is a decorator:

```python
class ToolFailure(Exception): ...        # expected: the agent can fix it

def tool(fn):
    @functools.wraps(fn)
    def wrapper(*a, **kw):
        try:
            return fn(*a, **kw)
        except ToolFailure as e:
            raise ToolError(str(e)) from e
    mcp.tool()(wrapper)
    return fn
```

Only *expected* failures are converted: bad SQL, a blocked statement, a missing file. A real
bug (an `AttributeError`) is deliberately left unconverted, so it shows up in the server's
log with a traceback and the agent gets the generic message. Do not catch `Exception` here;
that would swallow bugs and present them to the model as if it had made a mistake.

`main.py` includes a `query_unwrapped` tool *only* to demonstrate the difference, and
asserts the secret text is absent from what the client receives. The server's stderr
shows the full traceback, which is the point: the developer sees it, the model does not.

## The Shape of These Three Tools

- **`list_files`**: no arguments. The cheap first call that tells the agent what exists,
  in the same vocabulary the SQL will use.
- **`query`**: the workhorse. Its docstring states the file-naming rule, the row limit and
  the allowed statements.
- (Module 06 adds `describe_file`.)

Few, well-named tools beat many clever ones: each tool is something the model has to
choose between on every turn.

## The Flaw (on Purpose)

The last step of the demo writes a file *outside* the data folder and reads it back through
`query`:

```
outside the data folder: ['password', 'hunter2']
```

The gate decides which *statements* run, never which *files* they touch. That is Module 06.

## Run It

```bash
python 04-the-mcp-tool-wrapper/main.py
```

The output contains some server log lines (including the deliberate traceback) from the
subprocess, followed by the tool list, a table of order counts, the two error messages, and `OK`.

→ [Next: Module 05, Output Shaping](../05-output-shaping/README.md)
