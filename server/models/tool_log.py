from sqlalchemy import Column, Integer, Text, Numeric, DateTime
from server.db import Base
from datetime import datetime


class ToolLog(Base):
    __tablename__ = "tool_logs"

    id                = Column(Integer, primary_key=True, index=True)
    user_query        = Column(Text)
    tool_name         = Column(Text)
    input_params      = Column(Text)   # stored as JSON string (SQLite-safe)
    output            = Column(Text)   # stored as JSON string (SQLite-safe)
    response_time_ms  = Column(Numeric)
    created_at        = Column(DateTime, default=datetime.utcnow)