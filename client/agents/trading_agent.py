"""
client/agents/trading_agent.py — Trading specialist agent.

Owns: portfolio holdings, PnL, market prices.
Uses the ReAct reasoning loop — decides whether to fetch portfolio,
PnL, market prices, or a combination based on the question.
"""

from client.mcp.client import MCPClient
from client.agents.react import react_loop

TOOLS = {
    "get_trading_portfolio": "Get current stock holdings (symbol, quantity, avg purchase price)",
    "get_pnl":               "Calculate unrealised profit/loss per position vs current market price",
    "get_market_price":      "Get latest simulated price for a stock symbol (AAPL, TSLA, MSFT, GOOG, AMZN)",
}

PERSONA = (
    "the Trading Agent at a finance company. "
    "You analyse portfolios and trading performance. "
    "For portfolio questions, start with get_trading_portfolio. "
    "If asked about profit/loss or performance, call get_pnl. "
    "If asked about a specific stock price, call get_market_price with the symbol. "
    "Call multiple tools if the question requires a complete picture."
)


async def trading_agent(mcp: MCPClient, query: str, customer_id: int) -> dict:
    return await react_loop(
        mcp, query, customer_id,
        agent_name="trading_agent",
        persona=PERSONA,
        tools=TOOLS,
        rag_category="trading",
    )