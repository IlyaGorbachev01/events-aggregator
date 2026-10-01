from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Настройки приложения."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_name: str = "Events Aggregator"
    debug: bool = False

    # Стандартная переменная (если задана вручную)
    database_url: str | None = None

    # Переменные окружения LMS
    postgres_connection_string: str | None = None
    postgres_host: str | None = None
    postgres_port: str | None = None
    postgres_username: str | None = None
    postgres_password: str | None = None
    postgres_database_name: str | None = None

    # Events Provider API
    events_provider_base_url: str = "http://student-system-events-provider-web.student-system-events-provider.svc:8000"
    events_provider_api_key: str

    sync_interval_minutes: int = 1440

    # Outbox worker
    outbox_poll_interval_seconds: float = 5.0
    outbox_batch_size: int = 10
    outbox_max_attempts: int = 5
    outbox_backoff_base_seconds: float = 2.0
    outbox_backoff_max_seconds: float = 300.0
    outbox_backoff_jitter_ratio: float = 0.2

    # Notification service (Capashino)
    capashino_base_url: str = (
        "http://student-system-capashino-web.student-system-capashino.svc:8000"
    )
    capashino_api_key: str = ""
    capashino_timeout_seconds: float = 10.0

    # Идемпотентность POST /api/tickets
    idempotency_key_ttl_hours: int = 7

    @model_validator(mode="after")
    def build_database_url(self) -> "Settings":
        """Автоматически формирует корректный DATABASE_URL для asyncpg."""
        # 1. Если database_url уже задан, просто нормализуем его префикс
        if self.database_url:
            self.database_url = self.database_url.replace(
                "postgres://",
                "postgresql+asyncpg://",
                1,
            )
            self.database_url = self.database_url.replace(
                "postgresql://",
                "postgresql+asyncpg://",
                1,
            )
            return self

        # 2. Если есть готовая строка подключения от LMS, исправляем схему для asyncpg
        if self.postgres_connection_string:
            url = self.postgres_connection_string.replace(
                "postgres://",
                "postgresql+asyncpg://",
                1,
            )
            self.database_url = url.replace("postgresql://", "postgresql+asyncpg://", 1)
            return self

        # 3. Если есть разрозненные переменные LMS, собираем URL вручную
        if (
            self.postgres_host
            and self.postgres_username
            and self.postgres_password
            and self.postgres_database_name
        ):
            port = self.postgres_port or "5432"
            self.database_url = (
                f"postgresql+asyncpg://{self.postgres_username}:{self.postgres_password}"
                f"@{self.postgres_host}:{port}/{self.postgres_database_name}"
            )
            return self

        # 4. Если ничего не найдено, вызываем ошибку
        raise ValueError(
            "Необходимо указать DATABASE_URL или переменные POSTGRES_*"
            "для подключения к БД",
        )


settings = Settings()  # type: ignore[call-arg]
