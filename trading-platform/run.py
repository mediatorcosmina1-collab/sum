#!/usr/bin/env python3
"""Entry point — run with: python run.py"""
import uvicorn
import os
import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent))

from dotenv import load_dotenv
load_dotenv()

from backend.config import get_settings
settings = get_settings()

if __name__ == "__main__":
    print("\n" + "="*60)
    print("  AI Trading Platform")
    print(f"  Mode: {settings.t212_mode.upper()}")
    print(f"  Analysis every: {settings.analysis_interval_minutes} minutes")
    print(f"  Max position: {settings.max_position_pct}% of portfolio")
    print(f"  Stop-loss: {settings.stop_loss_pct}% | Take-profit: {settings.take_profit_pct}%")
    print(f"  Dashboard: http://localhost:{settings.port}")
    print("="*60 + "\n")

    if not settings.t212_api_key:
        print("WARNING: T212_API_KEY not set — trading will fail, but dashboard works")
    if not settings.anthropic_api_key:
        print("WARNING: ANTHROPIC_API_KEY not set — AI analysis will fail")
    print()

    uvicorn.run(
        "backend.main:app",
        host="0.0.0.0",
        port=settings.port,
        reload=False,
        log_level="info",
    )
