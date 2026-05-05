from client.security.permissions import ROLE_PERMISSIONS


def check_permission(agent_name: str, tool_name: str) -> bool:

    allowed_tools = ROLE_PERMISSIONS.get(agent_name, set())

    return tool_name in allowed_tools
