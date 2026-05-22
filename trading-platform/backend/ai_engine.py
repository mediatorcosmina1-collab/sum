import anthropic
import json
from typing import Optional
from .config import get_settings
from .database import log_analysis, save_chat_message, get_chat_history

settings = get_settings()

_client: Optional[anthropic.AsyncAnthropic] = None


def get_client() -> anthropic.AsyncAnthropic:
    global _client
    if _client is None:
        _client = anthropic.AsyncAnthropic(api_key=settings.anthropic_api_key)
    return _client


SYSTEM_PROMPT = """You are an elite quantitative trading analyst with 25+ years of experience at top-tier hedge funds and proprietary trading desks.

Your analytical framework combines:
- Technical analysis: trends, momentum, volatility, volume, multi-timeframe confluence
- Fundamental analysis: valuation, growth quality, sector dynamics, competitive positioning
- Risk management: always define risk before reward, protect capital above all else
- Market psychology: identify where the crowd is wrong, exploit sentiment extremes

You think like Ray Dalio (macro awareness, risk parity), Paul Tudor Jones (technical precision, discipline), and Jim Simons (data-driven, probabilistic).

CORE PRINCIPLES:
1. Capital preservation first — a 50% loss requires a 100% gain to recover
2. Only trade with multiple confluent signals — one indicator is noise, three is a signal
3. Cut losers fast, let winners run with trailing stops
4. Never FOMO into extended moves — wait for pullbacks to structure
5. Earnings and macro events are wildcards — reduce exposure beforehand
6. Volume confirms price action — moves on low volume are suspect
7. The trend is your friend until it ends — respect higher-timeframe trend direction

RISK SCORING:
- Confidence ≥ 85%: very high conviction, max position size
- Confidence 70-84%: high conviction, standard position size
- Confidence 55-69%: moderate, half position or skip
- Confidence < 55%: insufficient evidence, always SKIP

Always respond with valid JSON only. No markdown, no prose outside JSON."""


def _format_news(news: list[dict]) -> str:
    if not news:
        return "No recent news available."
    lines = []
    for n in news[:5]:
        lines.append(f"- {n.get('title', '')} ({n.get('source', '')})")
    return "\n".join(lines)


def _format_patterns(patterns: list[str]) -> str:
    if not patterns:
        return "None detected"
    labels = {
        "hammer": "Hammer (bullish reversal)",
        "doji": "Doji (indecision)",
        "shooting_star": "Shooting Star (bearish reversal)",
        "bullish_engulfing": "Bullish Engulfing (strong buy signal)",
        "bearish_engulfing": "Bearish Engulfing (strong sell signal)",
        "morning_star": "Morning Star (bullish reversal)",
        "evening_star": "Evening Star (bearish reversal)",
        "three_white_soldiers": "Three White Soldiers (strong uptrend)",
        "three_black_crows": "Three Black Crows (strong downtrend)",
    }
    return ", ".join(labels.get(p, p) for p in patterns)


async def analyze_ticker(ticker: str, market_data: dict, portfolio_context: dict) -> dict:
    client = get_client()

    held_position = portfolio_context.get("positions", {}).get(ticker)
    held_info = ""
    if held_position:
        pnl = held_position.get("ppl", 0)
        invested = max(held_position.get("investedValue", 1), 1)
        held_info = f"""
CURRENTLY HOLDING:
- Shares: {held_position.get('quantity', 0)}
- Avg Cost: ${held_position.get('averagePrice', 0):.2f}
- Current Value: ${held_position.get('currentValue', 0):.2f}
- Unrealised P&L: ${pnl:.2f} ({pnl / invested * 100:.1f}%)
"""

    patterns_str = _format_patterns(market_data.get("patterns", []))
    news_str = _format_news(market_data.get("news", []))

    rsi_1h = market_data.get("rsi_1h")
    rsi_1h_str = f"{rsi_1h}" if rsi_1h else "N/A"

    prompt = f"""Analyze this stock for a high-conviction trading decision:

TICKER: {ticker}
SECTOR: {market_data.get('sector', 'N/A')} | INDUSTRY: {market_data.get('industry', 'N/A')}

PRICE ACTION:
- Price: ${market_data.get('price', 'N/A')} | Open: ${market_data.get('open', 'N/A')} | H: ${market_data.get('high', 'N/A')} | L: ${market_data.get('low', 'N/A')}
- 1D: {market_data.get('change_1d_pct', 'N/A')}% | 1W: {market_data.get('change_1w_pct', 'N/A')}% | 1M: {market_data.get('change_1m_pct', 'N/A')}%
- 52W High: ${market_data.get('52w_high', 'N/A')} | 52W Low: ${market_data.get('52w_low', 'N/A')}
- Support (20d): ${market_data.get('support', 'N/A')} | Resistance (20d): ${market_data.get('resistance', 'N/A')}
- VWAP: ${market_data.get('vwap', 'N/A')}

MOMENTUM & OSCILLATORS:
- RSI (14, daily): {market_data.get('rsi', 'N/A')} | RSI (1h): {rsi_1h_str}
- Stochastic K/D: {market_data.get('stoch_k', 'N/A')} / {market_data.get('stoch_d', 'N/A')}
- Williams %R: {market_data.get('williams_r', 'N/A')}
- CCI: {market_data.get('cci', 'N/A')}

TREND:
- MACD: {market_data.get('macd', 'N/A')} | Signal: {market_data.get('macd_signal', 'N/A')} | Status: {market_data.get('macd_crossover', 'N/A')}
- ADX (trend strength): {market_data.get('adx', 'N/A')} (>25 = strong trend)
- Above EMA9: {market_data.get('above_ema_9', 'N/A')} | Above EMA50: {market_data.get('above_ema_50', 'N/A')} | Above SMA200: {market_data.get('above_sma_200', 'N/A')}
- EMA9: ${market_data.get('ema_9', 'N/A')} | EMA21: ${market_data.get('ema_21', 'N/A')} | EMA50: ${market_data.get('ema_50', 'N/A')} | SMA200: ${market_data.get('sma_200', 'N/A')}

VOLATILITY:
- Bollinger %B: {market_data.get('bb_pct', 'N/A')} (0=lower band, 1=upper band)
- BB Upper: ${market_data.get('bb_upper', 'N/A')} | Lower: ${market_data.get('bb_lower', 'N/A')}
- ATR: {market_data.get('atr', 'N/A')} | Beta: {market_data.get('beta', 'N/A')}

VOLUME:
- Volume: {market_data.get('volume', 'N/A')} ({market_data.get('volume_ratio', 'N/A')}x avg)
- OBV Trend: {market_data.get('obv_trend', 'N/A')}

CANDLESTICK PATTERNS (last 3 bars): {patterns_str}

FUNDAMENTALS:
- Market Cap: {market_data.get('market_cap', 'N/A')} | P/E: {market_data.get('pe_ratio', 'N/A')} | Forward P/E: {market_data.get('forward_pe', 'N/A')} | PEG: {market_data.get('peg_ratio', 'N/A')}
- Revenue Growth: {market_data.get('revenue_growth', 'N/A')} | Earnings Growth: {market_data.get('earnings_growth', 'N/A')} | Profit Margin: {market_data.get('profit_margin', 'N/A')}
- Analyst Target: ${market_data.get('analyst_target', 'N/A')} | Recommendation: {market_data.get('recommendation', 'N/A')}
- Short Float: {market_data.get('short_float', 'N/A')} | Dividend Yield: {market_data.get('dividend_yield', 'N/A')}
- Next Earnings: {market_data.get('earnings_date', 'N/A')}

RECENT NEWS:
{news_str}

PORTFOLIO CONTEXT:
- Cash Available: ${portfolio_context.get('cash', 0):.2f}
- Portfolio Value: ${portfolio_context.get('total_value', 0):.2f}
- Open Positions: {portfolio_context.get('position_count', 0)}/{portfolio_context.get('max_positions', 10)}
- Max Position Size: {portfolio_context.get('max_position_pct', 5)}% of portfolio
{held_info}

RISK PARAMETERS:
- Stop Loss: {portfolio_context.get('stop_loss_pct', 3)}% | Take Profit: {portfolio_context.get('take_profit_pct', 8)}%
- Trailing Stop: {portfolio_context.get('trailing_stop_pct', 2)}%

Respond ONLY with this JSON:
{{
  "action": "BUY" | "SELL" | "HOLD" | "SKIP",
  "confidence": <integer 0-100>,
  "reasoning": "<3-4 sentence explanation citing specific data points>",
  "key_signals": ["signal1", "signal2", "signal3"],
  "risk_factors": ["risk1", "risk2"],
  "price_target": <float or null>,
  "stop_loss_price": <float or null>,
  "suggested_quantity": <float or null>,
  "time_horizon": "short" | "medium" | "long",
  "pattern_assessment": "<1 sentence on candlestick pattern significance or null>",
  "news_impact": "positive" | "negative" | "neutral" | "mixed"
}}

Rules:
- SELL: only if we hold the position and evidence is bearish
- BUY: only if cash available, room for more positions, and evidence is genuinely bullish
- HOLD: holding and conditions are OK, no action needed
- SKIP: not holding and shouldn't buy
- confidence >= 70: execute | < 70: always SKIP"""

    try:
        message = await client.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=1024,
            system=[{
                "type": "text",
                "text": SYSTEM_PROMPT,
                "cache_control": {"type": "ephemeral"},
            }],
            messages=[{"role": "user", "content": prompt}],
        )
        raw = message.content[0].text.strip()
        result = json.loads(raw)

        await log_analysis(
            ticker=ticker,
            action=result.get("action", "SKIP"),
            confidence=result.get("confidence", 0),
            reasoning=result.get("reasoning", ""),
            price_target=result.get("price_target"),
            stop_loss=result.get("stop_loss_price"),
            signals=result.get("key_signals", []),
            patterns=market_data.get("patterns", []),
            news_sentiment=result.get("news_impact", "neutral"),
        )
        return result
    except json.JSONDecodeError as e:
        return {"action": "SKIP", "confidence": 0, "reasoning": f"AI parse error: {e}", "key_signals": []}
    except Exception as e:
        return {"action": "SKIP", "confidence": 0, "reasoning": f"AI error: {e}", "key_signals": []}


async def run_portfolio_review(portfolio: list[dict], cash: float, total_value: float) -> dict:
    client = get_client()

    positions_summary = []
    for p in portfolio:
        pnl_pct = (p.get("ppl", 0) / max(p.get("investedValue", 1), 1)) * 100
        positions_summary.append(
            f"- {p.get('ticker', '?')}: ${p.get('currentValue', 0):.0f} | "
            f"PnL: {pnl_pct:.1f}% | Qty: {p.get('quantity', 0)} | Sector: {p.get('sector', 'Unknown')}"
        )

    prompt = f"""Review this trading portfolio and provide strategic assessment.

PORTFOLIO:
Cash: ${cash:.2f} ({cash / max(total_value, 1) * 100:.1f}% of total)
Invested: ${total_value - cash:.2f}
Total Value: ${total_value:.2f}

Positions:
{chr(10).join(positions_summary) if positions_summary else "No positions currently"}

Assess: diversification, concentration risk, sector exposure, cash allocation, overall health.

Respond ONLY with this JSON:
{{
  "overall_health": "strong" | "good" | "neutral" | "weak" | "critical",
  "health_score": <0-100>,
  "summary": "<2-3 sentences on portfolio state>",
  "top_risks": ["risk1", "risk2", "risk3"],
  "opportunities": ["opp1", "opp2"],
  "suggested_actions": ["action1", "action2"],
  "cash_deployment_advice": "<1 sentence on what to do with cash>",
  "diversification_score": <0-100>,
  "concentration_warning": true | false
}}"""

    try:
        message = await client.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=1024,
            system=[{"type": "text", "text": SYSTEM_PROMPT, "cache_control": {"type": "ephemeral"}}],
            messages=[{"role": "user", "content": prompt}],
        )
        raw = message.content[0].text.strip()
        return json.loads(raw)
    except Exception as e:
        return {
            "overall_health": "neutral",
            "health_score": 50,
            "summary": f"Review failed: {e}",
            "top_risks": [],
            "opportunities": [],
            "suggested_actions": [],
            "cash_deployment_advice": "",
            "diversification_score": 50,
            "concentration_warning": False,
        }


async def get_market_sentiment() -> dict:
    client = get_client()
    try:
        message = await client.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=512,
            system=[{"type": "text", "text": SYSTEM_PROMPT, "cache_control": {"type": "ephemeral"}}],
            messages=[{
                "role": "user",
                "content": """Based on your training knowledge, provide a general market sentiment assessment.
Note: this reflects your knowledge cutoff, not live market data.

Respond ONLY with JSON:
{
  "sentiment": "very_bullish" | "bullish" | "neutral" | "bearish" | "very_bearish",
  "score": <-100 to 100>,
  "key_themes": ["theme1", "theme2", "theme3"],
  "sectors_to_watch": ["sector1", "sector2"],
  "macro_risks": ["risk1", "risk2"],
  "caution_note": "<1 sentence disclaimer about knowledge cutoff>"
}"""
            }],
        )
        raw = message.content[0].text.strip()
        return json.loads(raw)
    except Exception as e:
        return {"sentiment": "neutral", "score": 0, "key_themes": [], "sectors_to_watch": [], "macro_risks": [], "caution_note": str(e)}


async def generate_daily_brief(watchlist_data: list[dict], portfolio: list[dict], cash: float) -> dict:
    """Generate a morning market brief with key opportunities and risks for the day."""
    client = get_client()

    top_movers = sorted(watchlist_data, key=lambda x: abs(x.get("change_1d_pct", 0)), reverse=True)[:5]
    mover_lines = [f"- {d['ticker']}: {d.get('change_1d_pct', 0):+.1f}%, RSI {d.get('rsi', 'N/A')}"
                   for d in top_movers if "error" not in d]

    bullish = [d["ticker"] for d in watchlist_data if d.get("macd_crossover") == "bullish_crossover" and "error" not in d]
    bearish = [d["ticker"] for d in watchlist_data if d.get("macd_crossover") == "bearish_crossover" and "error" not in d]

    held = [p.get("ticker", "") for p in portfolio]

    prompt = f"""Generate a concise morning trading brief for today.

TOP MOVERS IN WATCHLIST:
{chr(10).join(mover_lines) if mover_lines else "No data"}

FRESH MACD CROSSOVERS:
- Bullish: {', '.join(bullish) if bullish else 'None'}
- Bearish: {', '.join(bearish) if bearish else 'None'}

CURRENT HOLDINGS: {', '.join(held) if held else 'None'}
CASH AVAILABLE: ${cash:.2f}

Provide actionable morning brief.

Respond ONLY with JSON:
{{
  "headline": "<1-sentence market summary>",
  "key_opportunities": ["opp1", "opp2", "opp3"],
  "key_risks": ["risk1", "risk2"],
  "tickers_to_watch": ["ticker1", "ticker2"],
  "suggested_focus": "<1-2 sentences on what to prioritize today>",
  "market_bias": "bullish" | "neutral" | "bearish"
}}"""

    try:
        message = await client.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=800,
            system=[{"type": "text", "text": SYSTEM_PROMPT, "cache_control": {"type": "ephemeral"}}],
            messages=[{"role": "user", "content": prompt}],
        )
        raw = message.content[0].text.strip()
        return json.loads(raw)
    except Exception as e:
        return {"headline": f"Brief generation failed: {e}", "key_opportunities": [], "key_risks": [], "tickers_to_watch": [], "suggested_focus": "", "market_bias": "neutral"}


async def ai_chat(user_message: str, portfolio_context: dict) -> str:
    """AI assistant for portfolio questions and trading advice."""
    client = get_client()

    history = await get_chat_history(limit=10)
    messages = []
    for h in history:
        messages.append({"role": h["role"], "content": h["content"]})

    positions = portfolio_context.get("positions", [])
    pos_lines = []
    for p in positions:
        pnl = p.get("ppl", 0)
        pos_lines.append(f"- {p.get('ticker', '?')}: {p.get('quantity', 0)} shares, P&L ${pnl:.2f}")

    context_block = f"""[PORTFOLIO CONTEXT]
Total Value: ${portfolio_context.get('total_value', 0):.2f}
Cash: ${portfolio_context.get('cash', 0):.2f}
Positions:
{chr(10).join(pos_lines) if pos_lines else 'None'}
"""

    full_message = f"{context_block}\n\nUser question: {user_message}"
    messages.append({"role": "user", "content": full_message})

    chat_system = SYSTEM_PROMPT + "\n\nYou are now in chat mode. Answer the user's trading questions clearly and concisely. Be direct and actionable. Use plain text, no JSON required here."

    try:
        response = await client.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=1024,
            system=[{"type": "text", "text": chat_system, "cache_control": {"type": "ephemeral"}}],
            messages=messages,
        )
        reply = response.content[0].text.strip()
        await save_chat_message("user", user_message)
        await save_chat_message("assistant", reply)
        return reply
    except Exception as e:
        return f"Chat error: {e}"
