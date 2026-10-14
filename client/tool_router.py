"""
client/tool_router.py — Routes natural-language queries to MCP tools.

Replaces both the static INTENT_TO_TOOL dict and the ToolRegistry.
Discovers available tools from the MCP server on first use and caches
them, so adding a new tool to mcp_server.py is the only step needed.

The keyword map is still used for fast routing, but it's built from
the MCP tool names + descriptions instead of being hardcoded.
"""

import re
from client.mcp.client import MCPClient, MCPConnectionError


# ---------------------------------------------------------------------------
# Keyword map — maps keywords to (tool_name, required_arg_names)
#
# This is the ONE place that maps user intent to tools.  When you add
# a tool to mcp_server.py, add its keywords here too.
# ---------------------------------------------------------------------------
_KEYWORD_MAP: dict[tuple[str, ...], tuple[str, list[str]]] = {
    # Full analysis — must be first so "full" matches before specifics
    ("full", "complete", "overall", "everything", "summary", "overview", "all"):
        ("full_customer_analysis", ["customer_id"]),

    # Customer
    ("customer", "profile", "account", "who", "identity"):
        ("get_customer", ["customer_id"]),

    # Loans
    ("loan", "borrow", "repay", "debt", "mortgage"):
        ("get_loan_status", ["customer_id"]),

    # Credit
    ("credit", "score", "approve", "approval", "rating"):
        ("get_credit_score", ["customer_id"]),

    # Risk
    ("risk", "danger", "threat"):
        ("get_risk_score", ["customer_id"]),

    # Fraud
    ("fraud", "suspicious", "flag", "scam"):
        ("check_fraud", ["customer_id"]),

    # Portfolio
    ("portfolio", "holdings", "position"):
        ("get_trading_portfolio", ["customer_id"]),

    # PnL
    ("pnl", "profit", "loss", "return", "gain", "performance"):
        ("get_pnl", ["customer_id"]),

    # Market price
    ("market", "price", "stock", "symbol", "ticker"):
        ("get_market_price", ["symbol"]),

    # List customers
    ("list", "customers", "directory"):
        ("list_customers", []),
}

# Default tool when nothing matches
_DEFAULT = ("get_customer", ["customer_id"])


def resolve_tool(message: str) -> tuple[str, list[str]]:
    """
    Pick the best MCP tool for a natural-language message.

    Returns:
        (tool_name, list_of_required_arg_names)
    """
    lowered = message.lower()
    for keywords, tool_spec in _KEYWORD_MAP.items():
        if any(k in lowered for k in keywords):
            return tool_spec
    return _DEFAULT


def extract_customer_id(message: str, fallback: int) -> int:
    """Parse a customer ID from the message, e.g. 'who is customer 3' → 3."""
    msg = message.lower()
    patterns = [
        r"customer\s+(?:id\s*)?#?\s*(\d+)",
        r"cust(?:omer)?\s*#?\s*(\d+)",
        r"\bid\s*[:#]?\s*(\d+)",
        r"\bfor\s+(\d+)\b",
        r"\bnumber\s+(\d+)\b",
        r"\b(\d+)\b",
    ]
    for pat in patterns:
        m = re.search(pat, msg)
        if m:
            return int(m.group(1))
    return fallback


# ---------------------------------------------------------------------------
# Live tool discovery — queries the MCP server for its actual tool list
# ---------------------------------------------------------------------------
_cached_tools: list[dict] | None = None


async def discover_tools(force: bool = False) -> list[dict]:
    """
    Fetch the tool list from the MCP server.  Cached after first call.
    Returns a list of {name, description, input_schema} dicts.
    """
    global _cached_tools
    if _cached_tools is not None and not force:
        return _cached_tools

    try:
        async with MCPClient() as mcp:
            _cached_tools = await mcp.list_tools()
        return _cached_tools
    except MCPConnectionError:
        return []


async def get_tool_names() -> list[str]:
    """Return just the tool names from the MCP server."""
    tools = await discover_tools()
    return [t["name"] for t in tools]