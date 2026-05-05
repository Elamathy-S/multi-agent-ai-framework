from sqlalchemy import Column, Integer, Numeric, Text, ForeignKey, DateTime
from server.db import Base
from datetime import datetime


class Transaction(Base):
    __tablename__ = "transactions"

    id = Column(Integer, primary_key=True, index=True)
    account_id = Column(Integer, ForeignKey("accounts.id"))
    amount = Column(Numeric, nullable=False)
    type = Column(Text)
    description = Column(Text)
    timestamp = Column(DateTime, default=datetime.utcnow)
