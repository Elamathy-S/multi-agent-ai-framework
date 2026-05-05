from sqlalchemy import Column, Integer, Float, String, ForeignKey
from server.db import Base

class Loan(Base):
    __tablename__ = "loans"

    id = Column(Integer, primary_key=True, index=True)
    customer_id = Column(Integer, ForeignKey("customers.id"))
    amount = Column(Float)
    interest_rate = Column(Float)
    term_months = Column(Integer, default=12)
    status = Column(String)  # approved / pending / rejected