"""
Core trading strategy engine.
Orchestrates: market data fetch → AI analysis → trade execution → logging.
"""
import asyncio
import math
from datetime import datetime
from typing import Optional

from .config import get_settings
from .t212_client import T212Client
from .market_data import get_multiple_tickers, get_ticker_data
from .ai_engine import analyze_ticker, run_portfolio_review
from .database import get_watchlist, log_trade, log_portfolio_snapshot

settings = get_settings()

# In-memory state (persisted to DB for history)
_last_run: Optional[str] = None
_is_running: bool = False
_status_log: list[str] = []


def _log(msg: str):
    ts = datetime.utcnow().strftime("%H:%M:%S")
    entry = f"[{ts}] {msg}"
    _status_log.append(entry)
    if len(_status_log) > 200:
        _status_log.pop(0)
    print(entry)


def get_status() -> dict:
    return {
        "is_running": _is_running,
        "last_run": _last_run,
        "log": _status_log[-50:],
    }


def _calc_position_size(available_cash: float, total_portfolio_value: float,
                         price: float, max_pct: float) -> float:
    """Calculate how many shares to buy based on max position % of total portfolio."""
    max_dollars = total_portfolio_value * (max_pct / 100)
    # Never use more than available cash
    dollars_to_use = min(max_dollars, available_cash * 0.95)  # keep 5% buffer
    if price <= 0 or dollars_to_use <= 0:
        return 0.0
    quantity = dollars_to_use / price
    # Round down to reasonable precision
    return math.floor(quantity * 100) / 100


async def run_analysis_cycle(client: T212Client) -> dict:
    """Full analysis + optional execution cycle."""
    global _last_run, _is_running

    if _is_running:
        return {"status": "already_running"}

    _is_running = True
    results = []

    try:
        _log("=== Analysis cycle started ===")

        # 1. Get account state
        _log("Fetching account data from Trading 212...")
        try:
            summary = await client.get_full_summary()
        except Exception as e:
            _log(f"ERROR: Cannot reach Trading 212 API: {e}")
            return {"status": "error", "message": str(e)}

        cash = summary["cash"]
        total_value = summary["total_value"]
        positions = {p["ticker"]: p for p in summary["positions"]}
        open_count = len(positions)

        _log(f"Account: ${total_value:.2f} total | ${cash:.2f} cash | {open_count} positions")

        # Log snapshot
        await log_portfolio_snapshot(
            total_value=total_value,
            cash=cash,
            invested=summary["invested"],
            pnl_day=0,  # T212 doesn't provide this directly
            pnl_total=summary["total_pnl"],
        )

        portfolio_context = {
            "cash": cash,
            "total_value": total_value,
            "position_count": open_count,
            "max_positions": settings.max_open_positions,
            "max_position_pct": settings.max_position_pct,
            "stop_loss_pct": settings.stop_loss_pct,
            "take_profit_pct": settings.take_profit_pct,
            "positions": positions,
        }

        # 2. Determine what to analyze
        watchlist = await get_watchlist()
        held_tickers = list(positions.keys())
        # Always include held tickers (for sell decisions)
        all_tickers = list(set(held_tickers + watchlist))

        _log(f"Analyzing {len(all_tickers)} tickers: {', '.join(all_tickers[:10])}...")

        # 3. Fetch market data in parallel
        market_data_list = await get_multiple_tickers(all_tickers)
        market_data_map = {d["ticker"]: d for d in market_data_list if "error" not in d}
        _log(f"Got market data for {len(market_data_map)} tickers")

        # 4. AI analysis in parallel (max 5 at a time to avoid rate limits)
        async def analyze_one(ticker: str):
            if ticker not in market_data_map:
                return None
            md = market_data_map[ticker]
            _log(f"  AI analyzing {ticker} @ ${md.get('price', '?')}...")
            analysis = await analyze_ticker(ticker, md, portfolio_context)
            return {"ticker": ticker, "market_data": md, "analysis": analysis}

        # Batch into groups of 5
        batch_size = 5
        for i in range(0, len(all_tickers), batch_size):
            batch = all_tickers[i:i + batch_size]
            batch_results = await asyncio.gather(*[analyze_one(t) for t in batch])
            for r in batch_results:
                if r:
                    results.append(r)
            if i + batch_size < len(all_tickers):
                await asyncio.sleep(1)  # brief pause between batches

        # 5. Execute decisions
        _log("--- Executing decisions ---")
        executed = []

        for item in results:
            ticker = item["ticker"]
            analysis = item["analysis"]
            md = item["market_data"]
            action = analysis.get("action", "SKIP")
            confidence = analysis.get("confidence", 0)
            price = md.get("price", 0)

            _log(f"  {ticker}: {action} (confidence: {confidence}%)")

            if action == "SKIP" or action == "HOLD":
                continue

            if confidence < settings.min_confidence:
                _log(f"    Skipping {ticker}: confidence {confidence}% < threshold {settings.min_confidence}%")
                continue

            if action == "BUY":
                if open_count >= settings.max_open_positions:
                    _log(f"    Skipping {ticker}: max positions reached ({open_count})")
                    continue
                if cash < 10:
                    _log(f"    Skipping {ticker}: insufficient cash (${cash:.2f})")
                    continue

                # Use AI-suggested quantity or calculate our own
                suggested_qty = analysis.get("suggested_quantity")
                if suggested_qty and suggested_qty > 0:
                    quantity = suggested_qty
                    # Cap at our max position size
                    max_qty = _calc_position_size(cash, total_value, price, settings.max_position_pct)
                    quantity = min(quantity, max_qty)
                else:
                    quantity = _calc_position_size(cash, total_value, price, settings.max_position_pct)

                if quantity <= 0:
                    _log(f"    Skipping {ticker}: calculated 0 shares")
                    continue

                cost = quantity * price
                _log(f"    BUYING {quantity} {ticker} @ ${price:.2f} = ${cost:.2f}")
                try:
                    order = await client.place_market_order(ticker, quantity)
                    order_id = str(order.get("id", ""))
                    await log_trade(
                        order_id=order_id,
                        ticker=ticker,
                        action="BUY",
                        quantity=quantity,
                        price=price,
                        status="placed",
                        reasoning=analysis.get("reasoning", ""),
                        confidence=confidence,
                    )
                    cash -= cost
                    open_count += 1
                    executed.append({"ticker": ticker, "action": "BUY", "quantity": quantity, "price": price})
                    _log(f"    ✓ Order placed: {order_id}")
                except Exception as e:
                    _log(f"    ✗ Order failed: {e}")

            elif action == "SELL":
                position = positions.get(ticker)
                if not position:
                    _log(f"    Skipping SELL {ticker}: not in portfolio")
                    continue

                quantity = position.get("quantity", 0)
                if quantity <= 0:
                    continue

                _log(f"    SELLING {quantity} {ticker} @ ${price:.2f}")
                try:
                    order = await client.place_market_order(ticker, -quantity)
                    order_id = str(order.get("id", ""))
                    pnl = (price - position.get("averagePrice", price)) * quantity
                    await log_trade(
                        order_id=order_id,
                        ticker=ticker,
                        action="SELL",
                        quantity=quantity,
                        price=price,
                        status="placed",
                        reasoning=analysis.get("reasoning", ""),
                        confidence=confidence,
                    )
                    executed.append({"ticker": ticker, "action": "SELL", "quantity": quantity, "price": price, "pnl": pnl})
                    _log(f"    ✓ Sell order placed: {order_id}")
                except Exception as e:
                    _log(f"    ✗ Sell order failed: {e}")

        _last_run = datetime.utcnow().isoformat()
        _log(f"=== Cycle complete. Executed {len(executed)} trades ===")

        return {
            "status": "success",
            "analyses": results,
            "executed": executed,
            "summary": {
                "tickers_analyzed": len(results),
                "trades_executed": len(executed),
                "cash_remaining": cash,
            }
        }

    finally:
        _is_running = False


async def check_stop_loss_take_profit(client: T212Client):
    """Check all held positions against stop-loss and take-profit levels."""
    _log("--- Checking stop-loss / take-profit ---")
    try:
        portfolio = await client.get_portfolio()
    except Exception as e:
        _log(f"SL/TP check failed: {e}")
        return

    for position in portfolio:
        ticker = position.get("ticker", "")
        avg_price = position.get("averagePrice", 0)
        current_price = position.get("currentPrice", 0)
        quantity = position.get("quantity", 0)

        if avg_price <= 0 or current_price <= 0 or quantity <= 0:
            continue

        pnl_pct = (current_price - avg_price) / avg_price * 100

        should_sell = False
        reason = ""

        if pnl_pct <= -settings.stop_loss_pct:
            should_sell = True
            reason = f"Stop-loss triggered: {pnl_pct:.1f}% loss"
        elif pnl_pct >= settings.take_profit_pct:
            should_sell = True
            reason = f"Take-profit triggered: +{pnl_pct:.1f}% gain"

        if should_sell:
            _log(f"  {ticker}: {reason} — selling {quantity} shares")
            try:
                order = await client.place_market_order(ticker, -quantity)
                order_id = str(order.get("id", ""))
                pnl = (current_price - avg_price) * quantity
                await log_trade(
                    order_id=order_id,
                    ticker=ticker,
                    action="SELL",
                    quantity=quantity,
                    price=current_price,
                    status="placed",
                    reasoning=reason,
                    confidence=95,
                )
                _log(f"  ✓ {ticker} sold. PnL: ${pnl:.2f}")
            except Exception as e:
                _log(f"  ✗ Failed to sell {ticker}: {e}")
