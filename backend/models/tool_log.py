from sqlalchemy import Column, Integer, Text, Numeric, DateTime
from sqlalchemy.dialects.postgresql import JSONB
from backend.db import Base
from datetime import datetime


class ToolLog(Base):
    __tablename__ = "tool_logs"

    id = Column(Integer, primary_key=True, index=True)

    user_query = Column(Text)
    tool_name = Column(Text)

    input_params = Column(JSONB)
    output = Column(JSONB)

    response_time_ms = Column(Numeric)

    created_at = Column(DateTime, default=datetime.utcnow)
