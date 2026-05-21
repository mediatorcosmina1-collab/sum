import aiosqlite
import json
from datetime import datetime
from pathlib import Path

DB_PATH = Path(__file__).parent.parent / "data" / "trading.db"


async def init_db():
    DB_PATH.parent.mkdir(exist_ok=True)
    async with aiosqlite.connect(DB_PATH) as db:
        await db.executescript("""
            CREATE TABLE IF NOT EXISTS trades (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                t212_order_id TEXT UNIQUE,
                ticker TEXT NOT NULL,
                action TEXT NOT NULL,
                quantity REAL NOT NULL,
                price REAL,
                status TEXT DEFAULT 'pending',
                ai_reasoning TEXT,
                confidence INTEGER,
                created_at TEXT DEFAULT (datetime('now')),
                closed_at TEXT,
                pnl REAL
            );

            CREATE TABLE IF NOT EXISTS ai_analyses (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                ticker TEXT NOT NULL,
                action TEXT NOT NULL,
                confidence INTEGER NOT NULL,
                reasoning TEXT NOT NULL,
                price_target REAL,
                stop_loss REAL,
                signals TEXT,
                created_at TEXT DEFAULT (datetime('now'))
            );

            CREATE TABLE IF NOT EXISTS portfolio_snapshots (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                total_value REAL,
                cash REAL,
                invested REAL,
                pnl_day REAL,
                pnl_total REAL,
                snapshot_at TEXT DEFAULT (datetime('now'))
            );

            CREATE TABLE IF NOT EXISTS watchlist (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                ticker TEXT UNIQUE NOT NULL,
                added_at TEXT DEFAULT (datetime('now'))
            );

            CREATE TABLE IF NOT EXISTS settings_store (
                key TEXT PRIMARY KEY,
                value TEXT
            );
        """)
        await db.commit()

        # Seed default watchlist
        default_tickers = [
            "AAPL", "MSFT", "NVDA", "GOOGL", "META",
            "AMZN", "TSLA", "AMD", "PLTR", "SOFI"
        ]
        for ticker in default_tickers:
            try:
                await db.execute(
                    "INSERT OR IGNORE INTO watchlist (ticker) VALUES (?)", (ticker,)
                )
            except Exception:
                pass
        await db.commit()


async def get_db():
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        yield db


async def log_trade(order_id, ticker, action, quantity, price, status, reasoning, confidence):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            """INSERT OR IGNORE INTO trades
               (t212_order_id, ticker, action, quantity, price, status, ai_reasoning, confidence)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (order_id, ticker, action, quantity, price, status, reasoning, confidence)
        )
        await db.commit()


async def log_analysis(ticker, action, confidence, reasoning, price_target, stop_loss, signals):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            """INSERT INTO ai_analyses
               (ticker, action, confidence, reasoning, price_target, stop_loss, signals)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (ticker, action, confidence, reasoning, price_target, stop_loss, json.dumps(signals))
        )
        await db.commit()


async def log_portfolio_snapshot(total_value, cash, invested, pnl_day, pnl_total):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            """INSERT INTO portfolio_snapshots (total_value, cash, invested, pnl_day, pnl_total)
               VALUES (?, ?, ?, ?, ?)""",
            (total_value, cash, invested, pnl_day, pnl_total)
        )
        await db.commit()


async def get_watchlist() -> list[str]:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT ticker FROM watchlist ORDER BY ticker") as cur:
            rows = await cur.fetchall()
            return [r["ticker"] for r in rows]


async def get_recent_trades(limit=50):
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT * FROM trades ORDER BY created_at DESC LIMIT ?", (limit,)
        ) as cur:
            return [dict(r) for r in await cur.fetchall()]


async def get_recent_analyses(limit=20):
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT * FROM ai_analyses ORDER BY created_at DESC LIMIT ?", (limit,)
        ) as cur:
            return [dict(r) for r in await cur.fetchall()]


async def get_portfolio_history(limit=288):
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT * FROM portfolio_snapshots ORDER BY snapshot_at DESC LIMIT ?", (limit,)
        ) as cur:
            rows = [dict(r) for r in await cur.fetchall()]
            return list(reversed(rows))
