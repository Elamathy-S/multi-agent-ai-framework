from sqlalchemy import Column, Integer, Float, String, ForeignKey
from backend.db import Base

class Loan(Base):
    __tablename__ = "loans"

    id = Column(Integer, primary_key=True, index=True)
    customer_id = Column(Integer, ForeignKey("customers.id"))
    amount = Column(Float)
    status = Column(String)
    interest_rate = Column(Float)