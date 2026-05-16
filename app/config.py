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

    source_extraction_interval_seconds: int = 1800
    source_extraction_limit: int = 25
    source_extraction_on_start: bool = False

    market_data_sources: str | None = None
    market_data_ingest_interval_seconds: int = 900
    market_data_ingest_limit: int = 10000
    market_data_ingest_on_start: bool = False

    angelone_api_key: str | None = None
    angelone_client_code: str | None = None
    angelone_pin: str | None = None
    angelone_totp_secret: str | None = None
    angelone_client_local_ip: str = "127.0.0.1"
    angelone_client_public_ip: str = "127.0.0.1"
    angelone_client_mac: str = "00:00:00:00:00:00"
    angelone_history_days: int = 5

    dhan_client_id: str | None = None
    dhan_access_token: str | None = None
    dhan_pin: str | None = None
    dhan_totp_secret: str | None = None
    dhan_history_days: int = 90
    dhan_token_cache_path: str = "/app/data/dhan_access_token.json"

    telegram_api_id: str | None = None
    telegram_api_hash: str | None = None
    telegram_bot_token: str | None = None
    telegram_session_name: str = "veda_telegram"
    telegram_session_dir: str = "/app/data/telegram"
    telegram_channels: str | None = None
    telegram_ingest_limit: int = 50

    x_bearer_token: str | None = None
    x_usernames: str | None = None
    x_ingest_interval_seconds: int = 3600
    x_ingest_limit: int = 20
    x_ingest_on_start: bool = False

    enable_live_trading: bool = False
    enable_paper_trading: bool = True
    paper_trading_symbols: str = "NIFTY,BANKNIFTY"
    paper_trading_timeframe: str = "5m"
    paper_trading_interval_seconds: int = 300
    paper_trading_candle_limit: int = 250
    paper_trading_quantity: int = 1
    paper_max_open_trades_per_symbol: int = 1
    paper_trade_cooldown_candles: int = 5
    paper_exit_mode: str = "author_part_book_trail"
    paper_part_book_r_multiple: float = 1.0
    paper_part_book_fraction: float = 0.5
    paper_trail_lookback_candles: int = 3
    paper_trading_on_start: bool = False
    global_kill_switch: bool = False
    max_daily_drawdown_pct: float = 1.0

    backup_dir: str = "/backups"

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")


settings = Settings()
