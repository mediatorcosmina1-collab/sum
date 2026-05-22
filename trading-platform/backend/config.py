from pydantic_settings import BaseSettings
from functools import lru_cache


class Settings(BaseSettings):
    t212_api_key: str = ""
    t212_mode: str = "demo"
    anthropic_api_key: str = ""

    # Position sizing
    max_position_pct: float = 5.0
    max_sector_pct: float = 35.0
    max_open_positions: int = 10

    # Analysis
    analysis_interval_minutes: int = 30
    min_confidence: int = 70

    # Risk management
    stop_loss_pct: float = 3.0
    take_profit_pct: float = 8.0
    trailing_stop_pct: float = 2.0        # trailing stop that follows price up
    daily_loss_limit_pct: float = 5.0     # auto-pause bot if portfolio drops this % in a day

    # Bot behaviour
    trade_market_hours_only: bool = True   # only execute during US market hours (9:30–16:00 ET)
    dca_mode: bool = False                 # buy more on dips in watchlist
    dca_drop_trigger_pct: float = 3.0     # DCA trigger: price dropped this % from 20d avg

    port: int = 8000

    @property
    def t212_base_url(self) -> str:
        if self.t212_mode == "live":
            return "https://live.trading212.com/api/v0"
        return "https://demo.trading212.com/api/v0"

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"


@lru_cache()
def get_settings() -> Settings:
    return Settings()
