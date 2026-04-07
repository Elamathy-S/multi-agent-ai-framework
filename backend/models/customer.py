from sqlalchemy import Column, Integer, String, Date
from backend.db import Base

class Customer(Base):
    __tablename__ = "customers"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String)
    email = Column(String)
    created_at = Column(Date)