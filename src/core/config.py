from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Настройки приложения."""

    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", extra="ignore"
    )

    app_name: str = "Events Aggregator"
    debug: bool = False

    database_url: str

    events_provider_base_url: str
    events_provider_api_key: str

    sync_interval_minutes: int = 1440


settings = Settings()  # type: ignore[call-arg]
