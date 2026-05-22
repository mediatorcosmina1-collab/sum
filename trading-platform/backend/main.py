from fastapi import FastAPI, HTTPException, BackgroundTasks
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Optional
from pathlib import Path
import asyncio

from .config import get_settings
from .database import (
    init_db, get_recent_trades, get_recent_analyses,
    get_portfolio_history, get_watchlist,
    get_alerts, add_alert, delete_alert,
    get_chat_history, clear_chat_history,
    get_performance_stats, log_trade,
)
from .t212_client import T212Client
from .market_data import get_ticker_data, get_price_history, get_news
from .ai_engine import analyze_ticker, run_portfolio_review, get_market_sentiment, generate_daily_brief, ai_chat
from .strategy import (
    run_analysis_cycle, check_stop_loss_take_profit,
    emergency_exit_all, pause_bot, resume_bot, get_status,
)
from apscheduler.schedulers.asyncio import AsyncIOScheduler

settings = get_settings()

app = FastAPI(title="AI Trading Platform", version="2.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

scheduler = AsyncIOScheduler()
t212 = T212Client()

FRONTEND_DIR = Path(__file__).parent.parent / "frontend"


# ── Lifespan ─────────────────────────────────────────────────────────────────

@app.on_event("startup")
async def startup():
    await init_db()
    scheduler.add_job(_run_cycle_job, "interval", minutes=settings.analysis_interval_minutes,
                      id="analysis_cycle", replace_existing=True)
    scheduler.add_job(_sl_tp_job, "interval", minutes=5, id="sl_tp_check", replace_existing=True)
    scheduler.start()
    print(f"Bot started. Analysis every {settings.analysis_interval_minutes}m | SL/TP/Trailing every 5m")


@app.on_event("shutdown")
async def shutdown():
    scheduler.shutdown(wait=False)


async def _run_cycle_job():
    await run_analysis_cycle(t212)


async def _sl_tp_job():
    await check_stop_loss_take_profit(t212)


# ── Static frontend ───────────────────────────────────────────────────────────

@app.get("/")
async def serve_index():
    return FileResponse(FRONTEND_DIR / "index.html")

@app.get("/app.js")
async def serve_js():
    return FileResponse(FRONTEND_DIR / "app.js")

@app.get("/styles.css")
async def serve_css():
    return FileResponse(FRONTEND_DIR / "styles.css")


# ── Account ───────────────────────────────────────────────────────────────────

@app.get("/api/account")
async def get_account():
    try:
        return await t212.get_full_summary()
    except Exception as e:
        raise HTTPException(status_code=502, detail=str(e))


@app.get("/api/portfolio")
async def get_portfolio():
    try:
        return await t212.get_portfolio()
    except Exception as e:
        raise HTTPException(status_code=502, detail=str(e))


# ── Market Data ───────────────────────────────────────────────────────────────

@app.get("/api/market/{ticker}")
async def market_data(ticker: str):
    data = await get_ticker_data(ticker.upper())
    if "error" in data:
        raise HTTPException(status_code=404, detail=data["error"])
    return data


@app.get("/api/market/{ticker}/history")
async def price_history(ticker: str, period: str = "1mo", interval: str = "1h"):
    return await get_price_history(ticker.upper(), period, interval)


@app.get("/api/market/{ticker}/news")
async def ticker_news(ticker: str):
    return await get_news(ticker.upper())


# ── AI Analysis ───────────────────────────────────────────────────────────────

@app.post("/api/analyze/{ticker}")
async def analyze_single(ticker: str):
    ticker = ticker.upper()
    md = await get_ticker_data(ticker)
    if "error" in md:
        raise HTTPException(status_code=404, detail=md["error"])
    try:
        summary = await t212.get_full_summary()
    except Exception:
        summary = {"cash": 0, "total_value": 0, "positions": []}
    context = {
        "cash": summary.get("cash", 0),
        "total_value": summary.get("total_value", 0),
        "position_count": len(summary.get("positions", [])),
        "max_positions": settings.max_open_positions,
        "max_position_pct": settings.max_position_pct,
        "stop_loss_pct": settings.stop_loss_pct,
        "take_profit_pct": settings.take_profit_pct,
        "trailing_stop_pct": settings.trailing_stop_pct,
        "positions": {p["ticker"]: p for p in summary.get("positions", [])},
    }
    result = await analyze_ticker(ticker, md, context)
    return {"ticker": ticker, "market_data": md, "analysis": result}


@app.post("/api/analyze/run")
async def trigger_analysis(background_tasks: BackgroundTasks):
    background_tasks.add_task(run_analysis_cycle, t212)
    return {"status": "started", "message": "Analysis cycle triggered"}


@app.get("/api/sentiment")
async def market_sentiment():
    return await get_market_sentiment()


@app.get("/api/portfolio/review")
async def portfolio_review():
    try:
        summary = await t212.get_full_summary()
        return await run_portfolio_review(
            summary.get("positions", []),
            summary.get("cash", 0),
            summary.get("total_value", 0),
        )
    except Exception as e:
        raise HTTPException(status_code=502, detail=str(e))


@app.get("/api/brief")
async def daily_brief():
    """Morning AI market brief."""
    try:
        watchlist = await get_watchlist()
        from .market_data import get_multiple_tickers
        wd = await get_multiple_tickers(watchlist[:10])
        try:
            summary = await t212.get_full_summary()
            portfolio = summary.get("positions", [])
            cash = summary.get("cash", 0)
        except Exception:
            portfolio, cash = [], 0
        return await generate_daily_brief(wd, portfolio, cash)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ── AI Chat ───────────────────────────────────────────────────────────────────

class ChatRequest(BaseModel):
    message: str


@app.post("/api/chat")
async def chat(req: ChatRequest):
    try:
        summary = await t212.get_full_summary()
        context = {
            "cash": summary.get("cash", 0),
            "total_value": summary.get("total_value", 0),
            "positions": summary.get("positions", []),
        }
    except Exception:
        context = {"cash": 0, "total_value": 0, "positions": []}
    reply = await ai_chat(req.message, context)
    return {"reply": reply}


@app.get("/api/chat/history")
async def chat_history():
    return await get_chat_history(limit=50)


@app.delete("/api/chat/history")
async def clear_chat():
    await clear_chat_history()
    return {"status": "cleared"}


# ── Manual Trading ────────────────────────────────────────────────────────────

class OrderRequest(BaseModel):
    ticker: str
    action: str
    quantity: float
    order_type: str = "market"
    limit_price: Optional[float] = None


@app.post("/api/order")
async def place_order(req: OrderRequest):
    ticker = req.ticker.upper()
    if req.action not in ("BUY", "SELL"):
        raise HTTPException(status_code=400, detail="action must be BUY or SELL")

    quantity = req.quantity if req.action == "BUY" else -abs(req.quantity)
    try:
        if req.order_type == "limit" and req.limit_price:
            order = await t212.place_limit_order(ticker, quantity, req.limit_price)
        else:
            order = await t212.place_market_order(ticker, quantity)

        await log_trade(
            order_id=str(order.get("id", "")),
            ticker=ticker,
            action=req.action,
            quantity=abs(req.quantity),
            price=req.limit_price,
            status="placed",
            reasoning="Manual order",
            confidence=100,
            strategy_tag="manual",
        )
        return order
    except Exception as e:
        raise HTTPException(status_code=502, detail=str(e))


@app.delete("/api/order/{order_id}")
async def cancel_order(order_id: int):
    try:
        return await t212.cancel_order(order_id)
    except Exception as e:
        raise HTTPException(status_code=502, detail=str(e))


@app.get("/api/orders")
async def list_orders():
    try:
        return await t212.get_orders()
    except Exception as e:
        raise HTTPException(status_code=502, detail=str(e))


@app.get("/api/orders/history")
async def order_history(limit: int = 50):
    try:
        return await t212.get_order_history(limit)
    except Exception as e:
        raise HTTPException(status_code=502, detail=str(e))


# ── Watchlist ─────────────────────────────────────────────────────────────────

@app.get("/api/watchlist")
async def watchlist():
    return await get_watchlist()


class WatchlistUpdate(BaseModel):
    ticker: str


@app.post("/api/watchlist")
async def add_to_watchlist(req: WatchlistUpdate):
    import aiosqlite
    from .database import DB_PATH
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("INSERT OR IGNORE INTO watchlist (ticker) VALUES (?)", (req.ticker.upper(),))
        await db.commit()
    return {"status": "added", "ticker": req.ticker.upper()}


@app.delete("/api/watchlist/{ticker}")
async def remove_from_watchlist(ticker: str):
    import aiosqlite
    from .database import DB_PATH
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("DELETE FROM watchlist WHERE ticker = ?", (ticker.upper(),))
        await db.commit()
    return {"status": "removed", "ticker": ticker.upper()}


# ── Alerts ────────────────────────────────────────────────────────────────────

class AlertRequest(BaseModel):
    ticker: str
    target_price: float
    direction: str   # "above" or "below"
    note: Optional[str] = ""


@app.get("/api/alerts")
async def list_alerts(include_triggered: bool = False):
    return await get_alerts(include_triggered=include_triggered)


@app.post("/api/alerts")
async def create_alert(req: AlertRequest):
    if req.direction not in ("above", "below"):
        raise HTTPException(status_code=400, detail="direction must be 'above' or 'below'")
    await add_alert(req.ticker, req.target_price, req.direction, req.note or "")
    return {"status": "created", "ticker": req.ticker.upper(), "target": req.target_price}


@app.delete("/api/alerts/{alert_id}")
async def remove_alert(alert_id: int):
    await delete_alert(alert_id)
    return {"status": "deleted"}


# ── History & Logs ────────────────────────────────────────────────────────────

@app.get("/api/trades")
async def trades(limit: int = 100):
    return await get_recent_trades(limit)


@app.get("/api/analyses")
async def analyses(limit: int = 30):
    return await get_recent_analyses(limit)


@app.get("/api/portfolio/history")
async def portfolio_history_endpoint(limit: int = 288):
    return await get_portfolio_history(limit)


@app.get("/api/status")
async def bot_status():
    return get_status()


# ── Performance ───────────────────────────────────────────────────────────────

@app.get("/api/performance")
async def performance():
    return await get_performance_stats()


# ── Bot Controls ──────────────────────────────────────────────────────────────

@app.post("/api/bot/pause")
async def bot_pause():
    pause_bot()
    return {"status": "paused"}


@app.post("/api/bot/resume")
async def bot_resume():
    resume_bot()
    return {"status": "resumed"}


@app.post("/api/bot/emergency-exit")
async def bot_emergency_exit(background_tasks: BackgroundTasks):
    background_tasks.add_task(emergency_exit_all, t212)
    return {"status": "emergency_exit_initiated", "message": "Selling all positions now. Bot paused."}


# ── Settings ──────────────────────────────────────────────────────────────────

@app.get("/api/settings")
async def get_settings_endpoint():
    return {
        "t212_mode": settings.t212_mode,
        "max_position_pct": settings.max_position_pct,
        "max_sector_pct": settings.max_sector_pct,
        "analysis_interval_minutes": settings.analysis_interval_minutes,
        "max_open_positions": settings.max_open_positions,
        "stop_loss_pct": settings.stop_loss_pct,
        "take_profit_pct": settings.take_profit_pct,
        "trailing_stop_pct": settings.trailing_stop_pct,
        "daily_loss_limit_pct": settings.daily_loss_limit_pct,
        "min_confidence": settings.min_confidence,
        "trade_market_hours_only": settings.trade_market_hours_only,
        "dca_mode": settings.dca_mode,
        "dca_drop_trigger_pct": settings.dca_drop_trigger_pct,
    }
