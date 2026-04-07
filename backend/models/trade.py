from sqlalchemy import Column, Integer, String, Float, ForeignKey, DateTime
from backend.db import Base

class Trade(Base):
    __tablename__ = "trades"

    id = Column(Integer, primary_key=True, index=True)
    customer_id = Column(Integer, ForeignKey("customers.id"))
    symbol = Column(String)
    quantity = Column(Float)
    price = Column(Float)
    trade_time = Column(DateTime)