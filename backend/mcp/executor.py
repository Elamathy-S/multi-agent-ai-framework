from backend.tools.tool_registry import registry


def execute_tool(tool_name: str, args: dict):

    tool = registry.get(tool_name)

    if not tool:
        return {"error": f"Tool {tool_name} not found"}

    try:
        result = tool["function"](**args)
        return {"result": result}

    except Exception as e:
        return {"error": str(e)}
