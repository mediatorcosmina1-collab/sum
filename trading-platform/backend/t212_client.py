import httpx
from typing import Optional
from .config import get_settings

settings = get_settings()


class T212Client:
    def __init__(self):
        self.base_url = settings.t212_base_url
        self.headers = {
            "Authorization": settings.t212_api_key,
            "Content-Type": "application/json",
        }

    async def _get(self, path: str, params: dict = None) -> dict:
        async with httpx.AsyncClient(timeout=30) as client:
            r = await client.get(f"{self.base_url}{path}", headers=self.headers, params=params)
            r.raise_for_status()
            return r.json()

    async def _post(self, path: str, body: dict) -> dict:
        async with httpx.AsyncClient(timeout=30) as client:
            r = await client.post(f"{self.base_url}{path}", headers=self.headers, json=body)
            r.raise_for_status()
            return r.json()

    async def _delete(self, path: str) -> dict:
        async with httpx.AsyncClient(timeout=30) as client:
            r = await client.delete(f"{self.base_url}{path}", headers=self.headers)
            r.raise_for_status()
            return r.json() if r.content else {}

    # ── Account ──────────────────────────────────────────────────────────────

    async def get_account_info(self) -> dict:
        return await self._get("/equity/account/info")

    async def get_cash(self) -> dict:
        return await self._get("/equity/account/cash")

    # ── Portfolio ─────────────────────────────────────────────────────────────

    async def get_portfolio(self) -> list[dict]:
        data = await self._get("/equity/portfolio")
        return data if isinstance(data, list) else data.get("items", [])

    async def get_position(self, ticker: str) -> Optional[dict]:
        try:
            return await self._get(f"/equity/portfolio/{ticker}")
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 404:
                return None
            raise

    # ── Orders ────────────────────────────────────────────────────────────────

    async def place_market_order(self, ticker: str, quantity: float) -> dict:
        """Buy (positive qty) or sell (negative qty) at market price."""
        return await self._post("/equity/orders/market", {
            "ticker": ticker,
            "quantity": quantity,
        })

    async def place_limit_order(self, ticker: str, quantity: float, limit_price: float,
                                 time_validity: str = "DAY") -> dict:
        return await self._post("/equity/orders/limit", {
            "ticker": ticker,
            "quantity": quantity,
            "limitPrice": limit_price,
            "timeValidity": time_validity,
        })

    async def place_stop_order(self, ticker: str, quantity: float, stop_price: float,
                                time_validity: str = "DAY") -> dict:
        return await self._post("/equity/orders/stop", {
            "ticker": ticker,
            "quantity": quantity,
            "stopPrice": stop_price,
            "timeValidity": time_validity,
        })

    async def cancel_order(self, order_id: int) -> dict:
        return await self._delete(f"/equity/orders/{order_id}")

    async def get_orders(self) -> list[dict]:
        data = await self._get("/equity/orders")
        return data if isinstance(data, list) else data.get("items", [])

    async def get_order_history(self, limit: int = 50) -> list[dict]:
        data = await self._get("/equity/history/orders", params={"limit": limit})
        return data if isinstance(data, list) else data.get("items", [])

    # ── Instruments ───────────────────────────────────────────────────────────

    async def search_instruments(self, query: str) -> list[dict]:
        data = await self._get("/equity/metadata/instruments")
        items = data if isinstance(data, list) else []
        query_lower = query.lower()
        return [i for i in items if query_lower in i.get("ticker", "").lower()
                or query_lower in i.get("name", "").lower()][:20]

    async def get_instrument_details(self, ticker: str) -> Optional[dict]:
        try:
            data = await self._get("/equity/metadata/instruments")
            items = data if isinstance(data, list) else []
            for item in items:
                if item.get("ticker", "").upper() == ticker.upper():
                    return item
            return None
        except Exception:
            return None

    # ── Pies ──────────────────────────────────────────────────────────────────

    async def get_pies(self) -> list[dict]:
        data = await self._get("/equity/pies")
        return data if isinstance(data, list) else data.get("items", [])

    # ── Summary ───────────────────────────────────────────────────────────────

    async def get_full_summary(self) -> dict:
        cash_data = await self.get_cash()
        portfolio = await self.get_portfolio()

        total_invested = sum(p.get("investedValue", 0) for p in portfolio)
        total_current = sum(p.get("currentValue", 0) for p in portfolio)
        cash = cash_data.get("freeForStocks", 0)

        return {
            "cash": cash,
            "invested": total_invested,
            "current_value": total_current,
            "total_value": cash + total_current,
            "total_pnl": total_current - total_invested,
            "total_pnl_pct": ((total_current - total_invested) / total_invested * 100)
                              if total_invested > 0 else 0,
            "positions": portfolio,
            "position_count": len(portfolio),
        }
