"""
client/mcp/executor.py — calls a named tool from the tool registry.
Used by gateway.py (REST) and can be reused by anything that needs
to invoke a tool by string name rather than direct function call.
"""

from server.tools.tool_registry import registry


def run_tool_by_name(tool_name: str, args: dict) -> dict:
    """
    Look up tool_name in the registry and call it with args.
    Returns the tool's result dict, or an error dict if not found.
    """
    tool = registry.get(tool_name)

    if not tool:
        return {"error": f"Tool '{tool_name}' not found in registry"}

    try:
        result = tool["function"](**args)
        return {"result": result}
    except TypeError as e:
        return {"error": f"Invalid arguments for '{tool_name}': {e}"}
    except Exception as e:
        return {"error": str(e)}