from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from sqlalchemy import DateTime, Index, String
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from src.core.database import Base


class IdempotencyKey(Base):
    """Ключ идемпотентности операции регистрации на мероприятие.

    Хранит связь «ключ идемпотентности -> результат успешной регистрации»
    для возврата того же билета при повторном запросе клиента (двойной
    клик, retry). ``request_hash`` позволяет обнаружить конфликт: тот же
    ключ, но другие данные запроса -> HTTP 409.
    """

    __tablename__ = "idempotency_keys"
    __table_args__ = (
        # Индекс по expires_at для эффективной очистки протухших ключей
        Index("ix_idempotency_keys_expires_at", "expires_at"),
    )

    key: Mapped[str] = mapped_column(String(128), primary_key=True)
    request_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    ticket_id: Mapped[str] = mapped_column(String, nullable=False)
    response: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC), nullable=False
    )
    expires_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
