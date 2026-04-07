import json
from backend.db import SessionLocal
from sqlalchemy import text


def log_tool_usage(user_query, tool_name, input_data, output_data, latency_ms):
    db = SessionLocal()

    try:
        db.execute(
            text("""
                INSERT INTO tool_logs 
                (user_query, tool_name, input_params, output, response_time_ms)
                VALUES (:uq, :tn, :inp, :out, :rt)
            """),
            {
                "uq": user_query,
                "tn": tool_name,
                "inp": json.dumps(input_data),
                "out": json.dumps(output_data),
                "rt": latency_ms
            }
        )

        db.commit()

    except Exception as e:
        db.rollback()
        print("❌ Logging failed:", str(e))

    finally:
        db.close()