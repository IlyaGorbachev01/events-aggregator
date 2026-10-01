from __future__ import annotations

import logging
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING, Any

from sqlalchemy import delete, func, select

from src.models.idempotency import IdempotencyKey

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)


class IdempotencyRepository:
    """Репозиторий ключей идемпотентности операций регистрации."""

    def __init__(self, session: AsyncSession) -> None:
        """Инициализация репозитория.

        Args:
            session: Сессия БД (транзакция вызывающего кода)
        """
        self._session = session

    async def get(self, key: str) -> IdempotencyKey | None:
        """Получить сохранённый результат по ключу идемпотентности.

        Args:
            key: Ключ идемпотентности из запроса клиента

        Returns:
            Запись с результатом либо None (ключ ещё не использован)
        """
        stmt = select(IdempotencyKey).where(IdempotencyKey.key == key)
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()

    async def save(
        self,
        key: str,
        request_hash: str,
        ticket_id: str,
        response: dict[str, Any],
        ttl_hours: int,
    ) -> IdempotencyKey:
        """Сохранить пару «ключ -> результат успешной регистрации».

        Вызывается только после успешного создания билета. Уникальность по
        PK обеспечивает гонку параллельных запросов с тем же ключом:
        проигравший получит IntegrityError (см. usecase).

        Args:
            key: Ключ идемпотентности
            request_hash: SHA-256 канонического тела запроса
            ticket_id: Идентификатор созданного билета
            response: Тело ответа для повторных запросов
            ttl_hours: Срок хранения ключа в часах

        Returns:
            Созданная запись
        """
        now = datetime.now(UTC)
        record = IdempotencyKey(
            key=key,
            request_hash=request_hash,
            ticket_id=ticket_id,
            response=response,
            created_at=now,
            expires_at=now + timedelta(hours=ttl_hours),
        )
        self._session.add(record)
        await self._session.flush()
        return record

    async def delete_expired(self) -> int:
        """Удалить протухшие ключи идемпотентности.

        Returns:
            Количество удалённых записей
        """
        stmt = (
            delete(IdempotencyKey)
            .where(IdempotencyKey.expires_at < datetime.now(UTC))
            .returning(func.count())
        )
        result = await self._session.execute(stmt)
        await self._session.flush()
        return result.scalar_one()
