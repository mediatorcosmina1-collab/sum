import yfinance as yf
import pandas as pd
import numpy as np
import asyncio
from functools import partial


# ── Indicator helpers ─────────────────────────────────────────────────────────

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

def _williams_r(high: pd.Series, low: pd.Series, close: pd.Series, n=14) -> pd.Series:
    hh = high.rolling(n).max()
    ll = low.rolling(n).min()
    return -100 * (hh - close) / (hh - ll).replace(0, np.nan)

def _cci(high: pd.Series, low: pd.Series, close: pd.Series, n=20) -> pd.Series:
    tp = (high + low + close) / 3
    sma_tp = tp.rolling(n).mean()
    mad = tp.rolling(n).apply(lambda x: np.abs(x - x.mean()).mean(), raw=True)
    return (tp - sma_tp) / (0.015 * mad.replace(0, np.nan))

def _adx(high: pd.Series, low: pd.Series, close: pd.Series, n=14) -> pd.Series:
    up_move = high.diff()
    down_move = -low.diff()
    pos_dm = up_move.where((up_move > down_move) & (up_move > 0), 0.0)
    neg_dm = down_move.where((down_move > up_move) & (down_move > 0), 0.0)
    atr = _atr(high, low, close, n)
    pos_di = 100 * _ema(pos_dm, n) / atr.replace(0, np.nan)
    neg_di = 100 * _ema(neg_dm, n) / atr.replace(0, np.nan)
    dx = 100 * (pos_di - neg_di).abs() / (pos_di + neg_di).replace(0, np.nan)
    return _ema(dx, n)

def _obv(close: pd.Series, volume: pd.Series) -> pd.Series:
    direction = np.sign(close.diff()).fillna(0)
    return (direction * volume).cumsum()

def _vwap_approx(high: pd.Series, low: pd.Series, close: pd.Series, volume: pd.Series) -> pd.Series:
    tp = (high + low + close) / 3
    return (tp * volume).cumsum() / volume.cumsum().replace(0, np.nan)

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

def _detect_candlestick_patterns(df: pd.DataFrame) -> list[str]:
    """Detect common candlestick patterns in the last few bars."""
    patterns = []
    if len(df) < 3:
        return patterns

    o = df["Open"]
    h = df["High"]
    l = df["Low"]
    c = df["Close"]

    # Current and previous bars
    c0, o0, h0, l0 = float(c.iloc[-1]), float(o.iloc[-1]), float(h.iloc[-1]), float(l.iloc[-1])
    c1, o1, h1, l1 = float(c.iloc[-2]), float(o.iloc[-2]), float(h.iloc[-2]), float(l.iloc[-2])
    c2, o2 = float(c.iloc[-3]), float(o.iloc[-3])

    body0 = abs(c0 - o0)
    body1 = abs(c1 - o1)
    range0 = h0 - l0 if h0 != l0 else 0.0001
    range1 = h1 - l1 if h1 != l1 else 0.0001
    upper_wick0 = h0 - max(c0, o0)
    lower_wick0 = min(c0, o0) - l0

    # Doji (very small body)
    if body0 / range0 < 0.1:
        patterns.append("doji")

    # Hammer (long lower wick, small body near top, bullish reversal)
    if lower_wick0 > 2 * body0 and upper_wick0 < body0 * 0.5 and c0 > o0:
        patterns.append("hammer")

    # Shooting star (long upper wick, small body near bottom, bearish reversal)
    if upper_wick0 > 2 * body0 and lower_wick0 < body0 * 0.5 and c0 < o0:
        patterns.append("shooting_star")

    # Bullish engulfing
    if c1 < o1 and c0 > o0 and c0 > o1 and o0 < c1:
        patterns.append("bullish_engulfing")

    # Bearish engulfing
    if c1 > o1 and c0 < o0 and c0 < o1 and o0 > c1:
        patterns.append("bearish_engulfing")

    # Morning star (3-bar bullish reversal)
    if c2 < o2 and body1 / range1 < 0.3 and c0 > o0 and c0 > (o2 + c2) / 2:
        patterns.append("morning_star")

    # Evening star (3-bar bearish reversal)
    if c2 > o2 and body1 / range1 < 0.3 and c0 < o0 and c0 < (o2 + c2) / 2:
        patterns.append("evening_star")

    # Three white soldiers (3 consecutive bullish bars)
    if c0 > o0 and c1 > o1 and c2 > o2 and c0 > c1 > c2:
        patterns.append("three_white_soldiers")

    # Three black crows (3 consecutive bearish bars)
    if c0 < o0 and c1 < o1 and c2 < o2 and c0 < c1 < c2:
        patterns.append("three_black_crows")

    return patterns

def _v(val):
    try:
        f = float(val)
        return None if (np.isnan(f) or np.isinf(f)) else round(f, 4)
    except Exception:
        return None


# ── News fetch ────────────────────────────────────────────────────────────────

def _fetch_news_sync(ticker: str) -> list[dict]:
    try:
        t = yf.Ticker(ticker)
        news = t.news or []
        out = []
        for item in news[:8]:
            content = item.get("content", {})
            title = content.get("title", item.get("title", ""))
            summary = content.get("summary", "")
            provider = content.get("provider", {})
            source = provider.get("displayName", "") if isinstance(provider, dict) else str(provider)
            pub_date = content.get("pubDate", item.get("providerPublishTime", ""))
            out.append({
                "title": title,
                "summary": summary[:200] if summary else "",
                "source": source,
                "published": str(pub_date),
            })
        return out
    except Exception:
        return []


async def get_news(ticker: str) -> list[dict]:
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(None, partial(_fetch_news_sync, ticker))


# ── Main fetch ────────────────────────────────────────────────────────────────

def _fetch_ticker_data_sync(ticker: str, period: str = "6mo") -> dict:
    try:
        t = yf.Ticker(ticker)
        df = t.history(period=period, interval="1d")
        if df.empty:
            return {"error": f"No data for {ticker}", "ticker": ticker}

        close  = df["Close"]
        high   = df["High"]
        low    = df["Low"]
        vol    = df["Volume"]
        open_  = df["Open"]

        # Standard indicators
        ema9   = _ema(close, 9)
        ema21  = _ema(close, 21)
        ema50  = _ema(close, 50)
        sma200 = _sma(close, min(200, len(df)))
        rsi_d  = _rsi(close)
        stk, std = _stochastic(high, low, close)
        macd_l, macd_s, macd_h = _macd(close)
        bb_upper, bb_mid, bb_lower, bb_pct = _bollinger(close)
        atr    = _atr(high, low, close)

        # Extended indicators
        willy  = _williams_r(high, low, close)
        cci_v  = _cci(high, low, close)
        adx_v  = _adx(high, low, close)
        obv_v  = _obv(close, vol)
        vwap_v = _vwap_approx(high, low, close, vol)

        # 1h RSI for multi-timeframe view
        rsi_1h = None
        try:
            df_1h = t.history(period="5d", interval="1h")
            if not df_1h.empty and len(df_1h) >= 14:
                rsi_1h = _v(_rsi(df_1h["Close"]).iloc[-1])
        except Exception:
            pass

        # Candlestick patterns
        patterns = _detect_candlestick_patterns(df)

        # News headlines
        news = _fetch_news_sync(ticker)

        last  = df.iloc[-1]
        prev  = df.iloc[-2] if len(df) > 1 else last
        w1    = df.iloc[-5]  if len(df) > 5  else df.iloc[0]
        m1    = df.iloc[-20] if len(df) > 20 else df.iloc[0]

        cp = float(last["Close"])
        pp = float(prev["Close"])

        # OBV trend: compare recent 5-day OBV to 20-day OBV avg
        obv_trend = "rising" if len(obv_v) >= 20 and float(obv_v.iloc[-1]) > float(obv_v.tail(20).mean()) else "falling"

        info = {}
        try:
            info = t.info or {}
        except Exception:
            pass

        # Earnings date
        earnings_date = None
        try:
            cal = t.calendar
            if cal is not None and not cal.empty:
                earnings_date = str(cal.iloc[0, 0]) if len(cal.columns) > 0 else None
        except Exception:
            pass

        return {
            "ticker":          ticker,
            "price":           round(cp, 4),
            "open":            _v(last["Open"]),
            "high":            _v(last["High"]),
            "low":             _v(last["Low"]),
            "volume":          int(last["Volume"]),
            "avg_volume":      int(vol.mean()),
            "volume_ratio":    round(float(last["Volume"]) / max(float(vol.mean()), 1), 2),
            "change_1d_pct":   round((cp - pp) / max(pp, 1e-9) * 100, 2),
            "change_1w_pct":   round((cp - float(w1["Close"])) / max(float(w1["Close"]), 1e-9) * 100, 2),
            "change_1m_pct":   round((cp - float(m1["Close"])) / max(float(m1["Close"]), 1e-9) * 100, 2),
            # Oscillators
            "rsi":             _v(rsi_d.iloc[-1]),
            "rsi_1h":          rsi_1h,
            "stoch_k":         _v(stk.iloc[-1]),
            "stoch_d":         _v(std.iloc[-1]),
            "williams_r":      _v(willy.iloc[-1]),
            "cci":             _v(cci_v.iloc[-1]),
            # Trend
            "macd":            _v(macd_l.iloc[-1]),
            "macd_signal":     _v(macd_s.iloc[-1]),
            "macd_diff":       _v(macd_h.iloc[-1]),
            "macd_crossover":  _detect_crossover(macd_h),
            "adx":             _v(adx_v.iloc[-1]),
            "ema_9":           _v(ema9.iloc[-1]),
            "ema_21":          _v(ema21.iloc[-1]),
            "ema_50":          _v(ema50.iloc[-1]),
            "sma_200":         _v(sma200.iloc[-1]),
            "above_ema_9":     bool(cp > float(ema9.iloc[-1])) if _v(ema9.iloc[-1]) else None,
            "above_ema_50":    bool(cp > float(ema50.iloc[-1])) if _v(ema50.iloc[-1]) else None,
            "above_sma_200":   bool(cp > float(sma200.iloc[-1])) if _v(sma200.iloc[-1]) else None,
            # Volatility / bands
            "bb_upper":        _v(bb_upper.iloc[-1]),
            "bb_lower":        _v(bb_lower.iloc[-1]),
            "bb_mid":          _v(bb_mid.iloc[-1]),
            "bb_pct":          _v(bb_pct.iloc[-1]),
            "atr":             _v(atr.iloc[-1]),
            # Volume
            "obv_trend":       obv_trend,
            "vwap":            _v(vwap_v.iloc[-1]),
            # Support / resistance
            "support":         round(float(low.tail(20).min()), 4),
            "resistance":      round(float(high.tail(20).max()), 4),
            # Patterns
            "patterns":        patterns,
            # Fundamentals
            "market_cap":      info.get("marketCap"),
            "pe_ratio":        info.get("trailingPE"),
            "forward_pe":      info.get("forwardPE"),
            "peg_ratio":       info.get("pegRatio"),
            "sector":          info.get("sector"),
            "industry":        info.get("industry"),
            "analyst_target":  info.get("targetMeanPrice"),
            "analyst_low":     info.get("targetLowPrice"),
            "analyst_high":    info.get("targetHighPrice"),
            "recommendation":  info.get("recommendationKey"),
            "short_float":     info.get("shortPercentOfFloat"),
            "beta":            info.get("beta"),
            "52w_high":        info.get("fiftyTwoWeekHigh"),
            "52w_low":         info.get("fiftyTwoWeekLow"),
            "revenue_growth":  info.get("revenueGrowth"),
            "earnings_growth": info.get("earningsGrowth"),
            "profit_margin":   info.get("profitMargins"),
            "dividend_yield":  info.get("dividendYield"),
            "earnings_date":   earnings_date,
            # News
            "news":            news,
        }
    except Exception as e:
        return {"error": str(e), "ticker": ticker}


async def get_ticker_data(ticker: str, period: str = "6mo") -> dict:
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
