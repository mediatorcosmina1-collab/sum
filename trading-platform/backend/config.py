from pydantic_settings import BaseSettings
from functools import lru_cache


class Settings(BaseSettings):
    t212_api_key: str = ""
    t212_mode: str = "demo"
    anthropic_api_key: str = ""
    max_position_pct: float = 5.0
    analysis_interval_minutes: int = 30
    max_open_positions: int = 10
    stop_loss_pct: float = 3.0
    take_profit_pct: float = 8.0
    min_confidence: int = 70
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
