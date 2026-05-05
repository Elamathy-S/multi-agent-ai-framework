from sqlalchemy import Column, Integer, Numeric, Text, ForeignKey, DateTime
from server.db import Base
from datetime import datetime


class FraudAlert(Base):
    __tablename__ = "fraud_alerts"

    id = Column(Integer, primary_key=True, index=True)
    transaction_id = Column(Integer, ForeignKey("transactions.id"))

    risk_score = Column(Numeric)
    status = Column(Text, default="open")

    created_at = Column(DateTime, default=datetime.utcnow)
