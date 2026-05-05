from sqlalchemy import Column, Integer, String, Numeric, TIMESTAMP
from server.db import Base
import datetime

class MarketPrice(Base):
    __tablename__ = "market_prices"

    id = Column(Integer, primary_key=True, index=True)
    symbol = Column(String, nullable=False)
    price = Column(Numeric, nullable=False)
    timestamp = Column(TIMESTAMP, default=datetime.datetime.utcnow)