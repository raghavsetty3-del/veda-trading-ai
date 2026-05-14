from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_env: str = "dev"
    app_name: str = "veda-trading-ai"
    app_secret_key: str = "change-me"

    database_url: str
    redis_url: str = "redis://redis:6379/0"

    chroma_host: str = "chroma"
    chroma_port: int = 8000

    openai_api_key: str | None = None
    openai_extraction_enabled: bool = False
    openai_extraction_model: str = "gpt-4.1-mini"

    blog_feeds: str | None = None
    blog_discovery_urls: str | None = None
    blog_ingest_interval_seconds: int = 3600
    blog_ingest_limit: int = 20
    blog_ingest_on_start: bool = False

    market_data_sources: str | None = None
    market_data_ingest_interval_seconds: int = 900
    market_data_ingest_limit: int = 5000
    market_data_ingest_on_start: bool = False

    telegram_api_id: str | None = None
    telegram_api_hash: str | None = None
    telegram_session_name: str = "veda_telegram"
    telegram_channels: str | None = None

    x_bearer_token: str | None = None
    x_usernames: str | None = None

    enable_live_trading: bool = False
    enable_paper_trading: bool = True
    paper_trading_symbols: str = "NIFTY,BANKNIFTY"
    paper_trading_timeframe: str = "5m"
    paper_trading_interval_seconds: int = 300
    paper_trading_candle_limit: int = 50
    paper_trading_quantity: int = 1
    paper_trading_on_start: bool = False
    global_kill_switch: bool = False
    max_daily_drawdown_pct: float = 1.0

    backup_dir: str = "/backups"

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")


settings = Settings()
