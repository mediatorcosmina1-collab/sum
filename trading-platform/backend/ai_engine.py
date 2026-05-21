import anthropic
import json
from typing import Optional
from .config import get_settings
from .database import log_analysis

settings = get_settings()

_client: Optional[anthropic.AsyncAnthropic] = None


def get_client() -> anthropic.AsyncAnthropic:
    global _client
    if _client is None:
        _client = anthropic.AsyncAnthropic(api_key=settings.anthropic_api_key)
    return _client


SYSTEM_PROMPT = """You are an elite quantitative trading analyst with 20+ years of experience at top hedge funds.
Your job is to analyze market data and make high-conviction trading decisions.

You think like Ray Dalio (macro awareness), Paul Tudor Jones (technical precision), and Jim Simons (data-driven).

When analyzing a stock, you:
1. Assess the technical picture: trend, momentum, volatility, volume
2. Consider fundamentals: valuation, growth, sector health
3. Evaluate risk/reward: where is the stop, where is the target
4. Make a decisive BUY, SELL, or HOLD call with a confidence score

You are CONSERVATIVE and protect capital above all. You only recommend BUY when you have multiple confirming signals.
You never chase. You never FOMO. You cut losses fast and let winners run.

Always respond with valid JSON only. No markdown, no prose outside JSON."""


async def analyze_ticker(ticker: str, market_data: dict, portfolio_context: dict) -> dict:
    """Run deep AI analysis on a single ticker and return a structured decision."""
    client = get_client()

    held_position = portfolio_context.get("positions", {}).get(ticker)
    held_info = ""
    if held_position:
        held_info = f"""
CURRENTLY HOLDING:
- Shares: {held_position.get('quantity', 0)}
- Avg Cost: ${held_position.get('averagePrice', 0):.2f}
- Current Value: ${held_position.get('currentValue', 0):.2f}
- P&L: ${held_position.get('ppl', 0):.2f} ({held_position.get('ppl', 0) / max(held_position.get('investedValue', 1), 1) * 100:.1f}%)
"""

    prompt = f"""Analyze this stock for a trading decision:

TICKER: {ticker}

TECHNICAL DATA:
- Price: ${market_data.get('price', 'N/A')}
- 1D Change: {market_data.get('change_1d_pct', 'N/A')}%
- 1W Change: {market_data.get('change_1w_pct', 'N/A')}%
- 1M Change: {market_data.get('change_1m_pct', 'N/A')}%
- Volume Ratio (vs avg): {market_data.get('volume_ratio', 'N/A')}x
- RSI (14): {market_data.get('rsi', 'N/A')}
- Stochastic K/D: {market_data.get('stoch_k', 'N/A')} / {market_data.get('stoch_d', 'N/A')}
- MACD Status: {market_data.get('macd_crossover', 'N/A')}
- MACD: {market_data.get('macd', 'N/A')} | Signal: {market_data.get('macd_signal', 'N/A')}
- Above EMA 9: {market_data.get('above_ema_9', 'N/A')}
- Above EMA 50: {market_data.get('above_ema_50', 'N/A')}
- Above SMA 200: {market_data.get('above_sma_200', 'N/A')}
- Bollinger % Position: {market_data.get('bb_pct', 'N/A')}
- ATR (volatility): {market_data.get('atr', 'N/A')}
- 20D Support: ${market_data.get('support', 'N/A')}
- 20D Resistance: ${market_data.get('resistance', 'N/A')}
- 52W High: ${market_data.get('52w_high', 'N/A')}
- 52W Low: ${market_data.get('52w_low', 'N/A')}
- Beta: {market_data.get('beta', 'N/A')}

FUNDAMENTALS:
- Market Cap: {market_data.get('market_cap', 'N/A')}
- P/E Ratio: {market_data.get('pe_ratio', 'N/A')}
- Forward P/E: {market_data.get('forward_pe', 'N/A')}
- PEG Ratio: {market_data.get('peg_ratio', 'N/A')}
- Revenue Growth: {market_data.get('revenue_growth', 'N/A')}
- Earnings Growth: {market_data.get('earnings_growth', 'N/A')}
- Profit Margin: {market_data.get('profit_margin', 'N/A')}
- Sector: {market_data.get('sector', 'N/A')}
- Analyst Target: ${market_data.get('analyst_target', 'N/A')}
- Analyst Recommendation: {market_data.get('recommendation', 'N/A')}
- Short Float: {market_data.get('short_float', 'N/A')}

PORTFOLIO CONTEXT:
- Available Cash: ${portfolio_context.get('cash', 0):.2f}
- Total Portfolio Value: ${portfolio_context.get('total_value', 0):.2f}
- Open Positions: {portfolio_context.get('position_count', 0)}/{portfolio_context.get('max_positions', 10)}
- Max Position Size: {portfolio_context.get('max_position_pct', 5)}% of portfolio
{held_info}

RISK PARAMETERS:
- Stop Loss: {portfolio_context.get('stop_loss_pct', 3)}% from entry
- Take Profit: {portfolio_context.get('take_profit_pct', 8)}% from entry

Respond with ONLY this JSON (no markdown, no extra text):
{{
  "action": "BUY" | "SELL" | "HOLD" | "SKIP",
  "confidence": <integer 0-100>,
  "reasoning": "<concise 2-3 sentence explanation of WHY>",
  "key_signals": ["signal1", "signal2", "signal3"],
  "price_target": <float or null>,
  "stop_loss_price": <float or null>,
  "suggested_quantity": <float or null>,
  "risk_factors": ["risk1", "risk2"],
  "time_horizon": "short" | "medium" | "long"
}}

SELL action: only if we currently hold the position.
BUY action: only if cash is available and we have room for more positions.
HOLD: we hold it and conditions look ok, no action needed.
SKIP: we don't hold it and shouldn't buy.
confidence >= 70 means execute, < 70 means skip."""

    try:
        message = await client.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=1024,
            system=SYSTEM_PROMPT,
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
        )
        return result
    except json.JSONDecodeError as e:
        return {"action": "SKIP", "confidence": 0, "reasoning": f"AI parse error: {e}", "key_signals": []}
    except Exception as e:
        return {"action": "SKIP", "confidence": 0, "reasoning": f"AI error: {e}", "key_signals": []}


async def run_portfolio_review(portfolio: list[dict], cash: float, total_value: float) -> dict:
    """High-level portfolio health review and rebalancing suggestions."""
    client = get_client()

    positions_summary = []
    for p in portfolio:
        pnl_pct = (p.get("ppl", 0) / max(p.get("investedValue", 1), 1)) * 100
        positions_summary.append(
            f"- {p.get('ticker', '?')}: ${p.get('currentValue', 0):.0f} | "
            f"PnL: {pnl_pct:.1f}% | Qty: {p.get('quantity', 0)}"
        )

    prompt = f"""Review my current trading portfolio and give strategic advice.

PORTFOLIO:
Cash: ${cash:.2f}
Invested: ${total_value - cash:.2f}
Total Value: ${total_value:.2f}
Positions:
{chr(10).join(positions_summary) if positions_summary else "No positions"}

Respond ONLY with this JSON:
{{
  "overall_health": "strong" | "good" | "neutral" | "weak" | "critical",
  "health_score": <0-100>,
  "summary": "<2-3 sentences on portfolio state>",
  "top_risks": ["risk1", "risk2"],
  "opportunities": ["opp1", "opp2"],
  "suggested_actions": ["action1", "action2"],
  "cash_deployment_advice": "<1 sentence on what to do with cash>"
}}"""

    try:
        message = await client.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=1024,
            system=SYSTEM_PROMPT,
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
        }


async def get_market_sentiment() -> dict:
    """Broad market sentiment analysis."""
    client = get_client()
    try:
        message = await client.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=512,
            system=SYSTEM_PROMPT,
            messages=[{
                "role": "user",
                "content": """Based on your training knowledge about typical market patterns and conditions,
provide a general market sentiment assessment. Note this is based on your knowledge cutoff, not live data.

Respond ONLY with JSON:
{
  "sentiment": "very_bullish" | "bullish" | "neutral" | "bearish" | "very_bearish",
  "score": <-100 to 100>,
  "key_themes": ["theme1", "theme2", "theme3"],
  "sectors_to_watch": ["sector1", "sector2"],
  "caution_note": "<1 sentence disclaimer about knowledge cutoff>"
}"""
            }],
        )
        raw = message.content[0].text.strip()
        return json.loads(raw)
    except Exception as e:
        return {"sentiment": "neutral", "score": 0, "key_themes": [], "sectors_to_watch": [], "caution_note": str(e)}
