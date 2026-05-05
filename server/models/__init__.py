# server/models/__init__.py
# Import all models here so Base.metadata.create_all() picks them up
# in a single import, regardless of which file calls it first.

from server.models.customer import Customer
from server.models.accounts import Account
from server.models.loans import Loan
from server.models.portfolio import Portfolio
from server.models.market import MarketPrice
from server.models.trade import Trade
from server.models.transactions import Transaction
from server.models.fraud_alert import FraudAlert
from server.models.tool_log import ToolLog
from server.models.agent_log import AgentLog

__all__ = [
    "Customer",
    "Account",
    "Loan",
    "Portfolio",
    "MarketPrice",
    "Trade",
    "Transaction",
    "FraudAlert",
    "ToolLog",
    "AgentLog",
]