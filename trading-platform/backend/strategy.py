"""
Core trading strategy engine.
Orchestrates: market data → AI analysis → execution → risk management.
"""
import asyncio
import math
from datetime import datetime, timezone
from typing import Optional

from .config import get_settings
from .t212_client import T212Client
from .market_data import get_multiple_tickers, get_ticker_data
from .ai_engine import analyze_ticker, run_portfolio_review
from .database import (
    get_watchlist, log_trade, log_portfolio_snapshot,
    get_alerts, trigger_alert,
    upsert_trailing_stop, get_trailing_stops, remove_trailing_stop,
    get_performance_stats,
)

settings = get_settings()

_last_run: Optional[str] = None
_is_running: bool = False
_is_paused: bool = False
_status_log: list[str] = []
_daily_start_value: Optional[float] = None
_daily_loss_triggered: bool = False


def _log(msg: str):
    ts = datetime.utcnow().strftime("%H:%M:%S")
    entry = f"[{ts}] {msg}"
    _status_log.append(entry)
    if len(_status_log) > 500:
        _status_log.pop(0)
    print(entry)


def get_status() -> dict:
    return {
        "is_running": _is_running,
        "is_paused": _is_paused,
        "daily_loss_triggered": _daily_loss_triggered,
        "last_run": _last_run,
        "log": _status_log[-80:],
    }


def pause_bot():
    global _is_paused
    _is_paused = True
    _log("⏸  Bot PAUSED by user")


def resume_bot():
    global _is_paused, _daily_loss_triggered
    _is_paused = False
    _daily_loss_triggered = False
    _log("▶  Bot RESUMED by user")


def _is_market_open() -> bool:
    """Returns True if US equity market is currently open (9:30–16:00 ET, Mon–Fri)."""
    now_utc = datetime.now(timezone.utc)
    # ET is UTC-4 (EDT) or UTC-5 (EST) — use UTC-4 as approximation (EDT)
    et_hour = (now_utc.hour - 4) % 24
    et_minute = now_utc.minute
    weekday = now_utc.weekday()  # Mon=0, Fri=4

    if weekday >= 5:
        return False

    market_open_mins  = 9 * 60 + 30   # 9:30 AM
    market_close_mins = 16 * 60        # 4:00 PM
    current_mins = et_hour * 60 + et_minute
    return market_open_mins <= current_mins < market_close_mins


def _calc_position_size(available_cash: float, total_portfolio_value: float,
                        price: float, max_pct: float) -> float:
    max_dollars = total_portfolio_value * (max_pct / 100)
    dollars_to_use = min(max_dollars, available_cash * 0.95)
    if price <= 0 or dollars_to_use <= 0:
        return 0.0
    return math.floor(dollars_to_use / price * 100) / 100


def _check_sector_limit(ticker_sector: str, positions: dict,
                        total_value: float, max_sector_pct: float) -> bool:
    """Returns True if adding to this sector would breach the sector concentration limit."""
    if not ticker_sector or total_value <= 0:
        return False
    sector_value = sum(
        p.get("currentValue", 0)
        for p in positions.values()
        if p.get("sector", "") == ticker_sector
    )
    return (sector_value / total_value * 100) >= max_sector_pct


def _check_daily_loss_limit(current_value: float) -> bool:
    """Returns True if daily loss limit has been breached."""
    global _daily_start_value
    if _daily_start_value is None or _daily_start_value <= 0:
        _daily_start_value = current_value
        return False
    drop_pct = (_daily_start_value - current_value) / _daily_start_value * 100
    return drop_pct >= settings.daily_loss_limit_pct


# ── Alert checker ─────────────────────────────────────────────────────────────

async def check_price_alerts(market_data_map: dict):
    """Trigger any price alerts whose conditions are now met."""
    alerts = await get_alerts(include_triggered=False)
    for alert in alerts:
        ticker = alert["ticker"]
        if ticker not in market_data_map:
            continue
        current_price = market_data_map[ticker].get("price", 0)
        target = alert["target_price"]
        direction = alert["direction"]

        hit = (direction == "above" and current_price >= target) or \
              (direction == "below" and current_price <= target)

        if hit:
            await trigger_alert(alert["id"])
            _log(f"🔔 ALERT: {ticker} hit ${current_price:.2f} (target: {direction} ${target:.2f})")


# ── Trailing stop manager ─────────────────────────────────────────────────────

async def update_trailing_stops(positions: dict):
    """Update peak prices and recalculate trailing stop levels for all held positions."""
    existing = await get_trailing_stops()
    for ticker, pos in positions.items():
        avg_price = pos.get("averagePrice", 0)
        current_price = pos.get("currentPrice", avg_price)
        if avg_price <= 0:
            continue

        if ticker in existing:
            peak = max(existing[ticker]["peak_price"], current_price)
        else:
            peak = current_price

        stop = peak * (1 - settings.trailing_stop_pct / 100)
        await upsert_trailing_stop(ticker, avg_price, peak, stop)


async def check_trailing_stops(client: T212Client, positions: dict):
    """Sell any position whose current price has fallen through the trailing stop."""
    trailing = await get_trailing_stops()

    for ticker, ts in trailing.items():
        if ticker not in positions:
            await remove_trailing_stop(ticker)
            continue

        pos = positions[ticker]
        current_price = pos.get("currentPrice", 0)
        stop_price = ts["stop_price"]

        if current_price <= 0 or stop_price <= 0:
            continue

        if current_price <= stop_price:
            quantity = pos.get("quantity", 0)
            if quantity <= 0:
                continue

            _log(f"  📉 {ticker}: trailing stop hit (${current_price:.2f} ≤ ${stop_price:.2f}). Selling.")
            try:
                order = await client.place_market_order(ticker, -quantity)
                await log_trade(
                    order_id=str(order.get("id", "")),
                    ticker=ticker,
                    action="SELL",
                    quantity=quantity,
                    price=current_price,
                    status="placed",
                    reasoning=f"Trailing stop triggered: price ${current_price:.2f} fell below stop ${stop_price:.2f}",
                    confidence=95,
                    strategy_tag="trailing_stop",
                )
                await remove_trailing_stop(ticker)
                _log(f"  ✓ {ticker} trailing stop sell placed")
            except Exception as e:
                _log(f"  ✗ Failed to sell {ticker} on trailing stop: {e}")


# ── Fixed stop-loss / take-profit ─────────────────────────────────────────────

async def check_stop_loss_take_profit(client: T212Client):
    _log("--- Checking stop-loss / take-profit ---")
    try:
        portfolio = await client.get_portfolio()
    except Exception as e:
        _log(f"SL/TP check failed: {e}")
        return

    positions = {p.get("ticker", ""): p for p in portfolio}

    # Update trailing stops while we're here
    await update_trailing_stops(positions)
    await check_trailing_stops(client, positions)

    for position in portfolio:
        ticker = position.get("ticker", "")
        avg_price = position.get("averagePrice", 0)
        current_price = position.get("currentPrice", 0)
        quantity = position.get("quantity", 0)

        if avg_price <= 0 or current_price <= 0 or quantity <= 0:
            continue

        pnl_pct = (current_price - avg_price) / avg_price * 100

        if pnl_pct <= -settings.stop_loss_pct:
            reason = f"Stop-loss: {pnl_pct:.1f}% loss (threshold: -{settings.stop_loss_pct}%)"
        elif pnl_pct >= settings.take_profit_pct:
            reason = f"Take-profit: +{pnl_pct:.1f}% gain (threshold: +{settings.take_profit_pct}%)"
        else:
            continue

        _log(f"  {ticker}: {reason} — selling {quantity} shares")
        try:
            order = await client.place_market_order(ticker, -quantity)
            pnl = (current_price - avg_price) * quantity
            await log_trade(
                order_id=str(order.get("id", "")),
                ticker=ticker,
                action="SELL",
                quantity=quantity,
                price=current_price,
                status="placed",
                reasoning=reason,
                confidence=95,
                strategy_tag="sl_tp",
            )
            await remove_trailing_stop(ticker)
            _log(f"  ✓ {ticker} sold. PnL: ${pnl:.2f}")
        except Exception as e:
            _log(f"  ✗ Failed to sell {ticker}: {e}")


# ── Emergency exit ────────────────────────────────────────────────────────────

async def emergency_exit_all(client: T212Client) -> dict:
    """Immediately sell every open position — emergency kill switch."""
    global _is_paused
    _is_paused = True
    _log("🚨 EMERGENCY EXIT: Selling all positions now!")

    try:
        portfolio = await client.get_portfolio()
    except Exception as e:
        _log(f"Emergency exit: could not fetch portfolio: {e}")
        return {"status": "error", "message": str(e)}

    results = []
    for pos in portfolio:
        ticker = pos.get("ticker", "")
        quantity = pos.get("quantity", 0)
        price = pos.get("currentPrice", 0)
        if quantity <= 0:
            continue
        try:
            order = await client.place_market_order(ticker, -quantity)
            await log_trade(
                order_id=str(order.get("id", "")),
                ticker=ticker,
                action="SELL",
                quantity=quantity,
                price=price,
                status="placed",
                reasoning="Emergency exit — all positions closed",
                confidence=100,
                strategy_tag="emergency",
            )
            await remove_trailing_stop(ticker)
            _log(f"  ✓ Emergency sold {quantity} {ticker} @ ${price:.2f}")
            results.append({"ticker": ticker, "quantity": quantity, "price": price, "status": "sold"})
        except Exception as e:
            _log(f"  ✗ Failed to emergency sell {ticker}: {e}")
            results.append({"ticker": ticker, "status": "failed", "error": str(e)})

    _log(f"Emergency exit complete. {len(results)} positions processed. Bot is PAUSED.")
    return {"status": "complete", "positions_processed": results, "bot_paused": True}


# ── DCA (Dollar-cost averaging) ───────────────────────────────────────────────

async def run_dca_cycle(client: T212Client, portfolio_context: dict, market_data_map: dict):
    """Buy dips: if a watchlist ticker has dropped >= dca_drop_trigger_pct from its SMA20, DCA in."""
    if not settings.dca_mode:
        return

    cash = portfolio_context.get("cash", 0)
    total_value = portfolio_context.get("total_value", 0)
    positions = portfolio_context.get("positions", {})

    _log("--- DCA cycle ---")
    for ticker, md in market_data_map.items():
        if "error" in md:
            continue
        price = md.get("price", 0)
        sma200 = md.get("sma_200")
        if not sma200 or price <= 0:
            continue

        drop_from_sma = (sma200 - price) / sma200 * 100
        if drop_from_sma < settings.dca_drop_trigger_pct:
            continue

        if cash < 10:
            break

        # Only DCA into stocks with RSI < 40 (genuinely oversold)
        rsi = md.get("rsi", 50)
        if rsi and rsi > 45:
            continue

        quantity = _calc_position_size(cash, total_value, price, settings.max_position_pct / 2)
        if quantity <= 0:
            continue

        _log(f"  DCA: {ticker} dropped {drop_from_sma:.1f}% from SMA200, RSI {rsi:.0f} — buying {quantity} shares")
        try:
            order = await client.place_market_order(ticker, quantity)
            await log_trade(
                order_id=str(order.get("id", "")),
                ticker=ticker,
                action="BUY",
                quantity=quantity,
                price=price,
                status="placed",
                reasoning=f"DCA: {drop_from_sma:.1f}% below SMA200, RSI {rsi:.0f}",
                confidence=60,
                strategy_tag="dca",
            )
            cash -= quantity * price
            _log(f"  ✓ DCA order placed for {ticker}")
        except Exception as e:
            _log(f"  ✗ DCA order failed for {ticker}: {e}")


# ── Main analysis cycle ───────────────────────────────────────────────────────

async def run_analysis_cycle(client: T212Client) -> dict:
    global _last_run, _is_running, _daily_start_value, _daily_loss_triggered

    if _is_running:
        return {"status": "already_running"}

    if _is_paused:
        _log("Bot is paused — skipping analysis cycle")
        return {"status": "paused"}

    if settings.trade_market_hours_only and not _is_market_open():
        _log("Market is closed — skipping analysis cycle (set TRADE_MARKET_HOURS_ONLY=false to override)")
        return {"status": "market_closed"}

    _is_running = True
    results = []

    try:
        _log("=== Analysis cycle started ===")

        # Account state
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

        # Daily loss check
        if _daily_start_value is None:
            _daily_start_value = total_value

        if _check_daily_loss_limit(total_value) and not _daily_loss_triggered:
            _daily_loss_triggered = True
            _is_paused = True
            _log(f"⚠️  Daily loss limit hit — portfolio down {settings.daily_loss_limit_pct}%+. Bot PAUSED.")
            return {"status": "daily_loss_limit_triggered"}

        await log_portfolio_snapshot(
            total_value=total_value,
            cash=cash,
            invested=summary["invested"],
            pnl_day=0,
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
            "trailing_stop_pct": settings.trailing_stop_pct,
            "positions": positions,
        }

        # Fetch market data
        watchlist = await get_watchlist()
        all_tickers = list(set(list(positions.keys()) + watchlist))
        _log(f"Analyzing {len(all_tickers)} tickers: {', '.join(all_tickers[:12])}...")

        market_data_list = await get_multiple_tickers(all_tickers)
        market_data_map = {d["ticker"]: d for d in market_data_list if "error" not in d}
        _log(f"Got market data for {len(market_data_map)} tickers")

        # Check price alerts
        await check_price_alerts(market_data_map)

        # AI analysis (batches of 5)
        async def analyze_one(ticker: str):
            if ticker not in market_data_map:
                return None
            md = market_data_map[ticker]
            _log(f"  AI analyzing {ticker} @ ${md.get('price', '?')} | RSI {md.get('rsi', '?')} | Patterns: {md.get('patterns', [])}")
            analysis = await analyze_ticker(ticker, md, portfolio_context)
            return {"ticker": ticker, "market_data": md, "analysis": analysis}

        batch_size = 5
        for i in range(0, len(all_tickers), batch_size):
            batch = all_tickers[i:i + batch_size]
            batch_results = await asyncio.gather(*[analyze_one(t) for t in batch])
            for r in batch_results:
                if r:
                    results.append(r)
            if i + batch_size < len(all_tickers):
                await asyncio.sleep(1)

        # Execute decisions
        _log("--- Executing decisions ---")
        executed = []

        for item in results:
            ticker = item["ticker"]
            analysis = item["analysis"]
            md = item["market_data"]
            action = analysis.get("action", "SKIP")
            confidence = analysis.get("confidence", 0)
            price = md.get("price", 0)

            _log(f"  {ticker}: {action} (conf: {confidence}%)")

            if action in ("SKIP", "HOLD"):
                continue
            if confidence < settings.min_confidence:
                _log(f"    → Skipped: conf {confidence}% < threshold {settings.min_confidence}%")
                continue

            if action == "BUY":
                if open_count >= settings.max_open_positions:
                    _log(f"    → Skipped: max positions ({open_count})")
                    continue
                if cash < 10:
                    _log(f"    → Skipped: insufficient cash (${cash:.2f})")
                    continue

                # Sector concentration check
                ticker_sector = md.get("sector", "")
                if _check_sector_limit(ticker_sector, positions, total_value, settings.max_sector_pct):
                    _log(f"    → Skipped: sector '{ticker_sector}' at concentration limit ({settings.max_sector_pct}%)")
                    continue

                suggested_qty = analysis.get("suggested_quantity")
                if suggested_qty and suggested_qty > 0:
                    max_qty = _calc_position_size(cash, total_value, price, settings.max_position_pct)
                    quantity = min(suggested_qty, max_qty)
                else:
                    quantity = _calc_position_size(cash, total_value, price, settings.max_position_pct)

                if quantity <= 0:
                    _log(f"    → Skipped: 0 shares calculated")
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
                        strategy_tag="ai",
                    )
                    # Start trailing stop tracking
                    await upsert_trailing_stop(ticker, price, price, price * (1 - settings.trailing_stop_pct / 100))
                    cash -= cost
                    open_count += 1
                    executed.append({"ticker": ticker, "action": "BUY", "quantity": quantity, "price": price})
                    _log(f"    ✓ Order placed: {order_id}")
                except Exception as e:
                    _log(f"    ✗ Order failed: {e}")

            elif action == "SELL":
                position = positions.get(ticker)
                if not position:
                    _log(f"    → Skipped SELL {ticker}: not in portfolio")
                    continue
                quantity = position.get("quantity", 0)
                if quantity <= 0:
                    continue

                _log(f"    SELLING {quantity} {ticker} @ ${price:.2f}")
                try:
                    order = await client.place_market_order(ticker, -quantity)
                    pnl = (price - position.get("averagePrice", price)) * quantity
                    await log_trade(
                        order_id=str(order.get("id", "")),
                        ticker=ticker,
                        action="SELL",
                        quantity=quantity,
                        price=price,
                        status="placed",
                        reasoning=analysis.get("reasoning", ""),
                        confidence=confidence,
                        strategy_tag="ai",
                    )
                    await remove_trailing_stop(ticker)
                    executed.append({"ticker": ticker, "action": "SELL", "quantity": quantity, "price": price, "pnl": pnl})
                    _log(f"    ✓ Sell placed (PnL: ${pnl:.2f})")
                except Exception as e:
                    _log(f"    ✗ Sell failed: {e}")

        # DCA pass
        await run_dca_cycle(client, portfolio_context, market_data_map)

        _last_run = datetime.utcnow().isoformat()
        _log(f"=== Cycle complete: {len(results)} analyzed, {len(executed)} executed ===")

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
