"""
client/logger.py — writes tool call logs to the tool_logs table.
Failures are printed but never raise, so a logging error never
breaks the actual tool call that triggered it.
"""

import json
from server.db import SessionLocal
from server.models.tool_log import ToolLog   # ensures table is in metadata


def log_tool_usage(
    user_query: str,
    tool_name: str,
    input_data: dict,
    output_data,
    latency_ms: float,
):
    db = SessionLocal()
    try:
        log = ToolLog(
            user_query       = user_query,
            tool_name        = tool_name,
            input_params     = json.dumps(input_data,  default=str),
            output           = json.dumps(output_data, default=str),
            response_time_ms = round(latency_ms, 2),
        )
        db.add(log)
        db.commit()
    except Exception as e:
        db.rollback()
        print(f"⚠️  Logging failed (non-fatal): {e}")
    finally:
        db.close()