import time
from sqlalchemy.orm import Session
from backend.models.portfolio import Portfolio
from backend.db import SessionLocal
from backend.logger import log_tool_usage
from backend.models.market import MarketPrice

def get_portfolio(customer_id: int):
    start = time.time()
    db: Session = SessionLocal()

    try:
        holdings = db.query(Portfolio).filter(
            Portfolio.customer_id == customer_id
        ).all()

        result = [
            {
                "symbol": h.symbol,
                "quantity": h.quantity,
                "avg_price": float(h.avg_purchase_price)
            }
            for h in holdings
        ]

        log_tool_usage(
            user_query=f"get_portfolio:{customer_id}",
            tool_name="get_portfolio",
            input_data={"customer_id": customer_id},
            output_data=result,
            latency_ms=round((time.time() - start) * 1000, 2)
        )

        return result

    except Exception as e:
        log_tool_usage(
            user_query=f"get_portfolio:{customer_id}",
            tool_name="get_portfolio",
            input_data={"customer_id": customer_id},
            output_data={"error": str(e)},
            latency_ms=round((time.time() - start) * 1000, 2)
        )
        raise

    finally:
        db.close()


def calculate_pnl(customer_id: int):
    start = time.time()
    db: Session = SessionLocal()

    try:
        holdings = db.query(Portfolio).filter(
            Portfolio.customer_id == customer_id
        ).all()

        result = []
        total_pnl = 0.0

        for h in holdings:
            market = db.query(MarketPrice).filter(
                MarketPrice.symbol == h.symbol
            ).first()

            if not market:
                continue

            current_price = float(market.price)
            avg_price = float(h.avg_purchase_price)
            quantity = h.quantity

            pnl = (current_price - avg_price) * quantity
            total_pnl += pnl

            result.append({
                "symbol": h.symbol,
                "quantity": quantity,
                "avg_price": avg_price,
                "current_price": current_price,
                "pnl": round(pnl, 2)
            })

        output = {
            "customer_id": customer_id,
            "total_pnl": round(total_pnl, 2),
            "holdings": result
        }

        log_tool_usage(
            user_query=f"calculate_pnl:{customer_id}",
            tool_name="calculate_pnl",
            input_data={"customer_id": customer_id},
            output_data=output,
            latency_ms=round((time.time() - start) * 1000, 2)
        )

        return output

    except Exception as e:
        log_tool_usage(
            user_query=f"calculate_pnl:{customer_id}",
            tool_name="calculate_pnl",
            input_data={"customer_id": customer_id},
            output_data={"error": str(e)},
            latency_ms=round((time.time() - start) * 1000, 2)
        )
        raise

    finally:
        db.close()