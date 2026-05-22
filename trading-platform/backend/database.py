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
                pnl REAL,
                strategy_tag TEXT
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
                patterns TEXT,
                news_sentiment TEXT,
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

            CREATE TABLE IF NOT EXISTS alerts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                ticker TEXT NOT NULL,
                target_price REAL NOT NULL,
                direction TEXT NOT NULL,
                note TEXT,
                triggered INTEGER DEFAULT 0,
                triggered_at TEXT,
                created_at TEXT DEFAULT (datetime('now'))
            );

            CREATE TABLE IF NOT EXISTS chat_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                role TEXT NOT NULL,
                content TEXT NOT NULL,
                created_at TEXT DEFAULT (datetime('now'))
            );

            CREATE TABLE IF NOT EXISTS trailing_stops (
                ticker TEXT PRIMARY KEY,
                entry_price REAL NOT NULL,
                peak_price REAL NOT NULL,
                stop_price REAL NOT NULL,
                updated_at TEXT DEFAULT (datetime('now'))
            );

            CREATE TABLE IF NOT EXISTS settings_store (
                key TEXT PRIMARY KEY,
                value TEXT
            );
        """)
        await db.commit()

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


# ── Trades ────────────────────────────────────────────────────────────────────

async def log_trade(order_id, ticker, action, quantity, price, status, reasoning, confidence,
                    strategy_tag: str = "ai"):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            """INSERT OR IGNORE INTO trades
               (t212_order_id, ticker, action, quantity, price, status, ai_reasoning, confidence, strategy_tag)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (order_id, ticker, action, quantity, price, status, reasoning, confidence, strategy_tag)
        )
        await db.commit()


async def get_recent_trades(limit=50):
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT * FROM trades ORDER BY created_at DESC LIMIT ?", (limit,)
        ) as cur:
            return [dict(r) for r in await cur.fetchall()]


# ── Analyses ──────────────────────────────────────────────────────────────────

async def log_analysis(ticker, action, confidence, reasoning, price_target, stop_loss,
                       signals, patterns=None, news_sentiment=None):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            """INSERT INTO ai_analyses
               (ticker, action, confidence, reasoning, price_target, stop_loss, signals, patterns, news_sentiment)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (ticker, action, confidence, reasoning, price_target, stop_loss,
             json.dumps(signals), json.dumps(patterns or []), news_sentiment or "")
        )
        await db.commit()


async def get_recent_analyses(limit=20):
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT * FROM ai_analyses ORDER BY created_at DESC LIMIT ?", (limit,)
        ) as cur:
            return [dict(r) for r in await cur.fetchall()]


# ── Portfolio snapshots ───────────────────────────────────────────────────────

async def log_portfolio_snapshot(total_value, cash, invested, pnl_day, pnl_total):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            """INSERT INTO portfolio_snapshots (total_value, cash, invested, pnl_day, pnl_total)
               VALUES (?, ?, ?, ?, ?)""",
            (total_value, cash, invested, pnl_day, pnl_total)
        )
        await db.commit()


async def get_portfolio_history(limit=288):
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT * FROM portfolio_snapshots ORDER BY snapshot_at DESC LIMIT ?", (limit,)
        ) as cur:
            rows = [dict(r) for r in await cur.fetchall()]
            return list(reversed(rows))


# ── Watchlist ─────────────────────────────────────────────────────────────────

async def get_watchlist() -> list[str]:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT ticker FROM watchlist ORDER BY ticker") as cur:
            rows = await cur.fetchall()
            return [r["ticker"] for r in rows]


# ── Alerts ────────────────────────────────────────────────────────────────────

async def get_alerts(include_triggered: bool = False):
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        if include_triggered:
            async with db.execute("SELECT * FROM alerts ORDER BY created_at DESC") as cur:
                return [dict(r) for r in await cur.fetchall()]
        else:
            async with db.execute(
                "SELECT * FROM alerts WHERE triggered = 0 ORDER BY created_at DESC"
            ) as cur:
                return [dict(r) for r in await cur.fetchall()]


async def add_alert(ticker: str, target_price: float, direction: str, note: str = ""):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "INSERT INTO alerts (ticker, target_price, direction, note) VALUES (?, ?, ?, ?)",
            (ticker.upper(), target_price, direction, note)
        )
        await db.commit()


async def trigger_alert(alert_id: int):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "UPDATE alerts SET triggered=1, triggered_at=datetime('now') WHERE id=?",
            (alert_id,)
        )
        await db.commit()


async def delete_alert(alert_id: int):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("DELETE FROM alerts WHERE id=?", (alert_id,))
        await db.commit()


# ── Chat history ──────────────────────────────────────────────────────────────

async def save_chat_message(role: str, content: str):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "INSERT INTO chat_history (role, content) VALUES (?, ?)", (role, content)
        )
        await db.commit()


async def get_chat_history(limit: int = 20):
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT * FROM chat_history ORDER BY created_at DESC LIMIT ?", (limit,)
        ) as cur:
            rows = [dict(r) for r in await cur.fetchall()]
            return list(reversed(rows))


async def clear_chat_history():
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("DELETE FROM chat_history")
        await db.commit()


# ── Trailing stops ────────────────────────────────────────────────────────────

async def upsert_trailing_stop(ticker: str, entry_price: float, peak_price: float, stop_price: float):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            """INSERT INTO trailing_stops (ticker, entry_price, peak_price, stop_price, updated_at)
               VALUES (?, ?, ?, ?, datetime('now'))
               ON CONFLICT(ticker) DO UPDATE SET
                 peak_price=excluded.peak_price,
                 stop_price=excluded.stop_price,
                 updated_at=excluded.updated_at""",
            (ticker.upper(), entry_price, peak_price, stop_price)
        )
        await db.commit()


async def get_trailing_stops() -> dict:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT * FROM trailing_stops") as cur:
            rows = await cur.fetchall()
            return {r["ticker"]: dict(r) for r in rows}


async def remove_trailing_stop(ticker: str):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("DELETE FROM trailing_stops WHERE ticker=?", (ticker.upper(),))
        await db.commit()


# ── Performance stats ─────────────────────────────────────────────────────────

async def get_performance_stats() -> dict:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row

        async with db.execute(
            "SELECT action, pnl, confidence, ticker, created_at FROM trades WHERE status != 'cancelled'"
        ) as cur:
            all_trades = [dict(r) for r in await cur.fetchall()]

        sells = [t for t in all_trades if t["action"] == "SELL" and t["pnl"] is not None]
        buys  = [t for t in all_trades if t["action"] == "BUY"]

        wins  = [t for t in sells if (t["pnl"] or 0) > 0]
        losses = [t for t in sells if (t["pnl"] or 0) <= 0]

        win_rate = len(wins) / len(sells) * 100 if sells else 0
        avg_win  = sum(t["pnl"] for t in wins) / len(wins) if wins else 0
        avg_loss = sum(t["pnl"] for t in losses) / len(losses) if losses else 0
        total_pnl = sum(t["pnl"] for t in sells)
        best_trade  = max((t["pnl"] for t in sells), default=0)
        worst_trade = min((t["pnl"] for t in sells), default=0)

        avg_confidence = (
            sum(t["confidence"] for t in all_trades if t["confidence"]) /
            len([t for t in all_trades if t["confidence"]])
            if any(t["confidence"] for t in all_trades) else 0
        )

        profit_factor = (
            abs(sum(t["pnl"] for t in wins)) / abs(sum(t["pnl"] for t in losses))
            if losses and sum(t["pnl"] for t in losses) != 0 else None
        )

        async with db.execute(
            "SELECT total_value, snapshot_at FROM portfolio_snapshots ORDER BY snapshot_at ASC LIMIT 1"
        ) as cur:
            first = await cur.fetchone()

        async with db.execute(
            "SELECT total_value FROM portfolio_snapshots ORDER BY snapshot_at DESC LIMIT 1"
        ) as cur:
            last = await cur.fetchone()

        portfolio_growth_pct = None
        if first and last and first["total_value"] and first["total_value"] > 0:
            portfolio_growth_pct = (last["total_value"] - first["total_value"]) / first["total_value"] * 100

        return {
            "total_trades": len(all_trades),
            "total_buys": len(buys),
            "total_sells": len(sells),
            "win_rate": round(win_rate, 1),
            "avg_win": round(avg_win, 2),
            "avg_loss": round(avg_loss, 2),
            "total_pnl": round(total_pnl, 2),
            "best_trade": round(best_trade, 2),
            "worst_trade": round(worst_trade, 2),
            "profit_factor": round(profit_factor, 2) if profit_factor else None,
            "avg_confidence": round(avg_confidence, 1),
            "portfolio_growth_pct": round(portfolio_growth_pct, 2) if portfolio_growth_pct is not None else None,
        }
