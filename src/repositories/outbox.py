from __future__ import annotations

import logging
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

from sqlalchemy import select, update

from src.core.enums import OutboxStatus
from src.models.outbox import OutboxMessage

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

    from src.core.enums import OutboxEventType

logger = logging.getLogger(__name__)


class OutboxRepository:
    """Репозиторий для работы с таблицей outbox."""

    def __init__(self, session: AsyncSession) -> None:
        """Инициализация репозитория outbox.

        Args:
            session: Сессия БД (транзакция вызывающего кода)
        """
        self._session = session

    async def add(
        self,
        event_type: OutboxEventType,
        payload: dict[str, Any],
    ) -> OutboxMessage:
        """Добавить запись в outbox в текущей транзакции.

        Args:
            event_type: Тип события
            payload: Данные события (JSON)

        Returns:
            Созданная запись outbox
        """
        message = OutboxMessage(event_type=event_type, payload=payload)
        self._session.add(message)
        await self._session.flush()
        return message

    async def fetch_pending(self, limit: int) -> list[OutboxMessage]:
        """Получить пачку неотправленных записей для обработки.

        Использует FOR UPDATE SKIP LOCKED, чтобы несколько экземпляров
        воркера не обрабатывали одну запись одновременно.

        Args:
            limit: Максимальное количество записей

        Returns:
            Список записей со статусом pending
        """
        stmt = (
            select(OutboxMessage)
            .where(OutboxMessage.status == OutboxStatus.PENDING)
            .order_by(OutboxMessage.created_at)
            .limit(limit)
            .with_for_update(skip_locked=True)
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def mark_sent(self, message_id: str) -> None:
        """Пометить запись как отправленную.

        Args:
            message_id: Идентификатор записи outbox
        """
        stmt = (
            update(OutboxMessage)
            .where(OutboxMessage.id == message_id)
            .values(
                status=OutboxStatus.SENT,
                sent_at=datetime.now(UTC),
            )
        )
        await self._session.execute(stmt)
        await self._session.flush()

    async def increment_attempts(self, message_id: str) -> None:
        """Увеличить счётчик попыток отправки.

        Args:
            message_id: Идентификатор записи outbox
        """
        stmt = (
            update(OutboxMessage)
            .where(OutboxMessage.id == message_id)
            .values(attempts=OutboxMessage.attempts + 1)
        )
        await self._session.execute(stmt)
        await self._session.flush()

    async def mark_failed(self, message_id: str) -> None:
        """Пометить запись как неуспешную (превышено число попыток).

        Args:
            message_id: Идентификатор записи outbox
        """
        stmt = (
            update(OutboxMessage)
            .where(OutboxMessage.id == message_id)
            .values(status=OutboxStatus.FAILED)
        )
        await self._session.execute(stmt)
        await self._session.flush()
