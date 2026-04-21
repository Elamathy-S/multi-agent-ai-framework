from sqlalchemy import Column, Integer, Numeric, Text, ForeignKey, DateTime
from backend.db import Base
from datetime import datetime


class Account(Base):
    __tablename__ = "accounts"

    id = Column(Integer, primary_key=True, index=True)

    customer_id = Column(
        Integer,
        ForeignKey("customers.id"),
        nullable=False
    )

    balance = Column(Numeric, default=0)

    account_type = Column(Text)  # checking / savings

    status = Column(Text, default="active")

    created_at = Column(DateTime, default=datetime.utcnow)
