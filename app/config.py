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

    blog_feeds: str | None = None
    blog_discovery_urls: str | None = None

    telegram_api_id: str | None = None
    telegram_api_hash: str | None = None
    telegram_session_name: str = "veda_telegram"
    telegram_channels: str | None = None

    x_bearer_token: str | None = None
    x_usernames: str | None = None

    enable_live_trading: bool = False
    enable_paper_trading: bool = True
    global_kill_switch: bool = False
    max_daily_drawdown_pct: float = 1.0

    backup_dir: str = "/backups"

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")


settings = Settings()
