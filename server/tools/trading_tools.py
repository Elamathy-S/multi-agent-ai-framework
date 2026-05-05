import time
from sqlalchemy.orm import Session
from server.models.portfolio import Portfolio
from server.db import SessionLocal
from server.logger import log_tool_usage
from server.models.market import MarketPrice

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

def execute_trade(customer_id: int, symbol: str, trade_type: str, quantity: int):
    """Execute a trade (buy or sell) for a customer"""
    start = time.time()
    db: Session = SessionLocal()

    try:
        from server.models.trade import Trade
        from datetime import datetime

        # Get current market price
        market = db.query(MarketPrice).filter(
            MarketPrice.symbol == symbol
        ).order_by(MarketPrice.timestamp.desc()).first()

        if not market:
            result = {"error": f"Market price not found for symbol {symbol}"}
            log_tool_usage(
                user_query=f"execute_trade:{customer_id}",
                tool_name="execute_trade",
                input_data={"customer_id": customer_id, "symbol": symbol, "trade_type": trade_type, "quantity": quantity},
                output_data=result,
                latency_ms=round((time.time() - start) * 1000, 2)
            )
            return result

        price = float(market.price)
        total_value = price * quantity

        # Create trade record
        trade = Trade(
            customer_id=customer_id,
            symbol=symbol,
            trade_type=trade_type,
            quantity=quantity,
            price=price,
            timestamp=datetime.now()
        )
        db.add(trade)

        # Update portfolio
        portfolio = db.query(Portfolio).filter(
            Portfolio.customer_id == customer_id,
            Portfolio.symbol == symbol
        ).first()

        if trade_type == "BUY":
            if portfolio:
                # Update existing position
                total_qty = portfolio.quantity + quantity
                total_cost = (portfolio.avg_purchase_price * portfolio.quantity) + (price * quantity)
                portfolio.quantity = total_qty
                portfolio.avg_purchase_price = total_cost / total_qty
            else:
                # Create new position
                portfolio = Portfolio(
                    customer_id=customer_id,
                    symbol=symbol,
                    quantity=quantity,
                    avg_purchase_price=price
                )
                db.add(portfolio)

        elif trade_type == "SELL":
            if not portfolio or portfolio.quantity < quantity:
                result = {"error": "Insufficient shares to sell"}
                log_tool_usage(
                    user_query=f"execute_trade:{customer_id}",
                    tool_name="execute_trade",
                    input_data={"customer_id": customer_id, "symbol": symbol, "trade_type": trade_type, "quantity": quantity},
                    output_data=result,
                    latency_ms=round((time.time() - start) * 1000, 2)
                )
                return result
            
            portfolio.quantity -= quantity
            if portfolio.quantity == 0:
                db.delete(portfolio)

        db.commit()

        result = {
            "status": "success",
            "trade_type": trade_type,
            "symbol": symbol,
            "quantity": quantity,
            "price": price,
            "total_value": round(total_value, 2),
            "timestamp": str(datetime.now())
        }

        log_tool_usage(
            user_query=f"execute_trade:{customer_id}",
            tool_name="execute_trade",
            input_data={"customer_id": customer_id, "symbol": symbol, "trade_type": trade_type, "quantity": quantity},
            output_data=result,
            latency_ms=round((time.time() - start) * 1000, 2)
        )

        return result

    except Exception as e:
        db.rollback()
        log_tool_usage(
            user_query=f"execute_trade:{customer_id}",
            tool_name="execute_trade",
            input_data={"customer_id": customer_id, "symbol": symbol, "trade_type": trade_type, "quantity": quantity},
            output_data={"error": str(e)},
            latency_ms=round((time.time() - start) * 1000, 2)
        )
        raise

    finally:
        db.close()