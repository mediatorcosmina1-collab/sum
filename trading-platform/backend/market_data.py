import yfinance as yf
import pandas as pd
import numpy as np
import asyncio
from functools import partial


# ── Pure-pandas indicator helpers ─────────────────────────────────────────────

def _ema(series: pd.Series, n: int) -> pd.Series:
    return series.ewm(span=n, adjust=False).mean()

def _sma(series: pd.Series, n: int) -> pd.Series:
    return series.rolling(n).mean()

def _rsi(series: pd.Series, n: int = 14) -> pd.Series:
    delta = series.diff()
    gain = delta.clip(lower=0).rolling(n).mean()
    loss = (-delta.clip(upper=0)).rolling(n).mean()
    rs = gain / loss.replace(0, np.nan)
    return 100 - 100 / (1 + rs)

def _macd(series: pd.Series, fast=12, slow=26, signal=9):
    macd_line = _ema(series, fast) - _ema(series, slow)
    signal_line = _ema(macd_line, signal)
    return macd_line, signal_line, macd_line - signal_line

def _bollinger(series: pd.Series, n=20, std_dev=2):
    mid = _sma(series, n)
    std = series.rolling(n).std()
    upper = mid + std_dev * std
    lower = mid - std_dev * std
    pband = (series - lower) / ((upper - lower).replace(0, np.nan))
    return upper, mid, lower, pband

def _stochastic(high: pd.Series, low: pd.Series, close: pd.Series, k=14, d=3):
    lowest_low = low.rolling(k).min()
    highest_high = high.rolling(k).max()
    k_pct = 100 * (close - lowest_low) / (highest_high - lowest_low).replace(0, np.nan)
    d_pct = k_pct.rolling(d).mean()
    return k_pct, d_pct

def _atr(high: pd.Series, low: pd.Series, close: pd.Series, n=14) -> pd.Series:
    hl = high - low
    hpc = (high - close.shift()).abs()
    lpc = (low - close.shift()).abs()
    tr = pd.concat([hl, hpc, lpc], axis=1).max(axis=1)
    return tr.rolling(n).mean()

def _detect_crossover(macd_diff: pd.Series) -> str:
    if len(macd_diff) < 2:
        return "neutral"
    prev = macd_diff.iloc[-2]
    curr = macd_diff.iloc[-1]
    if pd.isna(prev) or pd.isna(curr):
        return "neutral"
    if prev <= 0 < curr:
        return "bullish_crossover"
    if prev >= 0 > curr:
        return "bearish_crossover"
    return "bullish" if curr > 0 else "bearish"

def _v(val):
    """Return rounded float or None."""
    try:
        f = float(val)
        return None if (np.isnan(f) or np.isinf(f)) else round(f, 4)
    except Exception:
        return None


# ── Main fetch ────────────────────────────────────────────────────────────────

def _fetch_ticker_data_sync(ticker: str, period: str = "3mo") -> dict:
    try:
        t = yf.Ticker(ticker)
        df = t.history(period=period, interval="1d")
        if df.empty:
            return {"error": f"No data for {ticker}", "ticker": ticker}

        close = df["Close"]
        high  = df["High"]
        low   = df["Low"]
        vol   = df["Volume"]

        # Indicators
        ema9  = _ema(close, 9)
        ema21 = _ema(close, 21)
        ema50 = _ema(close, 50)
        sma200 = _sma(close, min(200, len(df)))
        rsi   = _rsi(close)
        stk, std = _stochastic(high, low, close)
        macd_l, macd_s, macd_h = _macd(close)
        bb_upper, bb_mid, bb_lower, bb_pct = _bollinger(close)
        atr   = _atr(high, low, close)

        last  = df.iloc[-1]
        prev  = df.iloc[-2] if len(df) > 1 else last
        w1    = df.iloc[-5] if len(df) > 5 else df.iloc[0]
        m1    = df.iloc[-20] if len(df) > 20 else df.iloc[0]

        cp = float(last["Close"])
        pp = float(prev["Close"])

        # Fundamentals
        info = {}
        try:
            info = t.info or {}
        except Exception:
            pass

        return {
            "ticker": ticker,
            "price":          round(cp, 4),
            "open":           _v(last["Open"]),
            "high":           _v(last["High"]),
            "low":            _v(last["Low"]),
            "volume":         int(last["Volume"]),
            "avg_volume":     int(vol.mean()),
            "volume_ratio":   round(float(last["Volume"]) / max(float(vol.mean()), 1), 2),
            "change_1d_pct":  round((cp - pp) / max(pp, 1e-9) * 100, 2),
            "change_1w_pct":  round((cp - float(w1["Close"])) / max(float(w1["Close"]), 1e-9) * 100, 2),
            "change_1m_pct":  round((cp - float(m1["Close"])) / max(float(m1["Close"]), 1e-9) * 100, 2),
            "rsi":            _v(rsi.iloc[-1]),
            "stoch_k":        _v(stk.iloc[-1]),
            "stoch_d":        _v(std.iloc[-1]),
            "macd":           _v(macd_l.iloc[-1]),
            "macd_signal":    _v(macd_s.iloc[-1]),
            "macd_diff":      _v(macd_h.iloc[-1]),
            "macd_crossover": _detect_crossover(macd_h),
            "ema_9":          _v(ema9.iloc[-1]),
            "ema_21":         _v(ema21.iloc[-1]),
            "ema_50":         _v(ema50.iloc[-1]),
            "sma_200":        _v(sma200.iloc[-1]),
            "above_ema_9":    bool(cp > float(ema9.iloc[-1])) if _v(ema9.iloc[-1]) else None,
            "above_ema_50":   bool(cp > float(ema50.iloc[-1])) if _v(ema50.iloc[-1]) else None,
            "above_sma_200":  bool(cp > float(sma200.iloc[-1])) if _v(sma200.iloc[-1]) else None,
            "bb_upper":       _v(bb_upper.iloc[-1]),
            "bb_lower":       _v(bb_lower.iloc[-1]),
            "bb_mid":         _v(bb_mid.iloc[-1]),
            "bb_pct":         _v(bb_pct.iloc[-1]),
            "atr":            _v(atr.iloc[-1]),
            "support":        round(float(low.tail(20).min()), 4),
            "resistance":     round(float(high.tail(20).max()), 4),
            "market_cap":     info.get("marketCap"),
            "pe_ratio":       info.get("trailingPE"),
            "forward_pe":     info.get("forwardPE"),
            "peg_ratio":      info.get("pegRatio"),
            "sector":         info.get("sector"),
            "industry":       info.get("industry"),
            "analyst_target": info.get("targetMeanPrice"),
            "analyst_low":    info.get("targetLowPrice"),
            "analyst_high":   info.get("targetHighPrice"),
            "recommendation": info.get("recommendationKey"),
            "short_float":    info.get("shortPercentOfFloat"),
            "beta":           info.get("beta"),
            "52w_high":       info.get("fiftyTwoWeekHigh"),
            "52w_low":        info.get("fiftyTwoWeekLow"),
            "revenue_growth": info.get("revenueGrowth"),
            "earnings_growth":info.get("earningsGrowth"),
            "profit_margin":  info.get("profitMargins"),
        }
    except Exception as e:
        return {"error": str(e), "ticker": ticker}


async def get_ticker_data(ticker: str, period: str = "3mo") -> dict:
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(None, partial(_fetch_ticker_data_sync, ticker, period))


async def get_multiple_tickers(tickers: list[str]) -> list[dict]:
    tasks = [get_ticker_data(t) for t in tickers]
    results = await asyncio.gather(*tasks, return_exceptions=True)
    out = []
    for i, r in enumerate(results):
        if isinstance(r, Exception):
            out.append({"ticker": tickers[i], "error": str(r)})
        else:
            out.append(r)
    return out


def _get_price_history_sync(ticker: str, period: str = "1mo", interval: str = "1h") -> list[dict]:
    try:
        df = yf.Ticker(ticker).history(period=period, interval=interval)
        if df.empty:
            return []
        return [
            {
                "time":   str(idx),
                "open":   round(float(r["Open"]), 4),
                "high":   round(float(r["High"]), 4),
                "low":    round(float(r["Low"]), 4),
                "close":  round(float(r["Close"]), 4),
                "volume": int(r["Volume"]),
            }
            for idx, r in df.iterrows()
        ]
    except Exception:
        return []


async def get_price_history(ticker: str, period: str = "1mo", interval: str = "1h") -> list[dict]:
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(None, partial(_get_price_history_sync, ticker, period, interval))
