from sqlalchemy import Column, Integer, String, Float, ForeignKey
from server.db import Base

class Portfolio(Base):
    __tablename__ = "portfolio"

    id = Column(Integer, primary_key=True, index=True)
    customer_id = Column(Integer, ForeignKey("customers.id"))
    symbol = Column(String)
    quantity = Column(Float)
    avg_purchase_price = Column(Float)