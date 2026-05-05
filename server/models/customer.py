from sqlalchemy import Column, Integer, String, Date
from server.db import Base
from datetime import date

class Customer(Base):
    __tablename__ = "customers"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, nullable=False)
    email = Column(String, nullable=False)
    created_at = Column(Date, default=date.today)