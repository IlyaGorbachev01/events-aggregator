from __future__ import annotations

import logging
import random
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING, Any

from sqlalchemy import func, select, update

from src.core.enums import OutboxStatus
from src.models.outbox import OutboxMessage

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

    from src.core.enums import OutboxEventType

logger = logging.getLogger(__name__)

# Максимальная длина сохраняемого текста ошибки (last_error)
MAX_ERROR_LENGTH = 500


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
        now = datetime.now(UTC)
        message = OutboxMessage(
            # StrEnum сохраняем явно через .value — исключаем риск
            # записи repr-подобного значения и рассогласования с
            # условием частичного индекса (status = 'pending')
            event_type=event_type.value,
            payload=payload,
            status=OutboxStatus.PENDING.value,
            attempts=0,
            next_attempt_at=now,
        )
        self._session.add(message)
        await self._session.flush()
        return message

    async def fetch_pending(self, limit: int) -> list[OutboxMessage]:
        """Получить пачку записей, готовых к отправке.

        Учитывается backoff: выбираются только pending-записи, у которых
        наступил срок следующей попытки (next_attempt_at <= now).

        Использует FOR UPDATE SKIP LOCKED, чтобы несколько экземпляров
        воркера не обрабатывали одну запись одновременно.

        Args:
            limit: Максимальное количество записей

        Returns:
            Список записей, готовых к обработке
        """
        now = datetime.now(UTC)
        stmt = (
            select(OutboxMessage)
            .where(
                OutboxMessage.status == OutboxStatus.PENDING.value,
                OutboxMessage.next_attempt_at <= now,
            )
            .order_by(OutboxMessage.created_at, OutboxMessage.next_attempt_at)
            .limit(limit)
            .with_for_update(skip_locked=True)
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def get_for_update(self, message_id: str) -> OutboxMessage | None:
        """Зафиксировать одну запись с блокировкой строки.

        Используется воркером перед доставкой: повторная блокировка
        гарантирует, что запись не обрабатывается параллельно другим
        экземпляром воркера и её статус актуален.

        Args:
            message_id: Идентификатор записи outbox

        Returns:
            Запись или None, если она отсутствует
        """
        stmt = (
            select(OutboxMessage)
            .where(OutboxMessage.id == message_id)
            .with_for_update(skip_locked=True)
        )
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()

    async def mark_sent(self, message_id: str) -> None:
        """Пометить запись как отправленную.

        Args:
            message_id: Идентификатор записи outbox
        """
        stmt = (
            update(OutboxMessage)
            .where(OutboxMessage.id == message_id)
            .values(
                status=OutboxStatus.SENT.value,
                sent_at=datetime.now(UTC),
                last_error=None,
            )
        )
        await self._session.execute(stmt)
        await self._session.flush()

    async def register_retry(
        self,
        message: OutboxMessage,
        error: str,
        *,
        max_attempts: int,
        backoff_base_seconds: float,
        backoff_max_seconds: float,
        backoff_jitter_ratio: float = 0.0,
    ) -> bool:
        """Зафиксировать неудачную попытку доставки.

        Увеличивает счётчик попыток, сохраняет текст ошибки и назначает
        срок следующей попытки с экспоненциальным backoff
        (base * 2^(attempts-1), но не более backoff_max_seconds).

        Если число попыток превысило max_attempts, запись помечается
        как failed и больше не будет выбираться воркером.

        Args:
            message: Зафиксированная воркером запись (FOR UPDATE) —
                передаётся целиком, чтобы не перечитывать её повторно
            error: Текст последней ошибки
            max_attempts: Максимальное число попыток
            backoff_base_seconds: Основание экспоненциального backoff
            backoff_max_seconds: Верхняя граница интервала повторной попытки
            backoff_jitter_ratio: Доля случайного «размытия» задержки
                (0..1); по умолчанию 0 — без размытия

        Returns:
            True, если запись переведена в failed (лимит попыток исчерпан)
        """
        now = datetime.now(UTC)
        # Читаем число попыток из уже зафиксированного воркером объекта:
        # повторный SELECT не нужен, а арифметика над колонкой
        # (ColumnElement[int]) не типизируется mypy как int. Python-арифметика
        # здесь безопасна, т.к. запись зафиксирована воркером (FOR UPDATE).
        new_attempts = message.attempts + 1
        delay_seconds = min(
            # 2 ** (int - 1): оба операнда — чистые int, без ColumnElement
            backoff_base_seconds * (2 ** (new_attempts - 1)),
            backoff_max_seconds,
        )
        if backoff_jitter_ratio > 0:
            # Равномерное размытие задержки в пределах +/-ratio*delay:
            # предотвращает синхронные волны повторов после простоя сервиса.
            jitter = random.uniform(-backoff_jitter_ratio, backoff_jitter_ratio)
            delay_seconds = max(delay_seconds * (1 + jitter), 0.0)
        # Python-bool вместо SQLAlchemy-выражения: возврат строго bool
        is_exhausted: bool = new_attempts >= max_attempts
        stmt = (
            update(OutboxMessage)
            .where(OutboxMessage.id == message.id)
            .values(
                attempts=new_attempts,
                last_error=error[:MAX_ERROR_LENGTH],
                status=(
                    OutboxStatus.FAILED.value
                    if is_exhausted
                    else OutboxStatus.PENDING.value
                ),
                next_attempt_at=now + timedelta(seconds=delay_seconds),
            )
        )
        await self._session.execute(stmt)
        await self._session.flush()
        return is_exhausted

    async def requeue_failed(self, message_id: str) -> bool:
        """Вернуть failed-запись в очередь для повторной доставки.

        Служебная операция для ручного re-drive событий, исчерпавших лимит
        попыток (например, после долгого простоя Capashino). Счётчик
        попыток обнуляется, backoff — с нуля.

        Args:
            message_id: Идентификатор записи outbox

        Returns:
            True, если запись найдена в статусе failed и переведена в pending
        """
        now = datetime.now(UTC)
        stmt = (
            update(OutboxMessage)
            .where(
                OutboxMessage.id == message_id,
                OutboxMessage.status == OutboxStatus.FAILED.value,
            )
            .values(
                status=OutboxStatus.PENDING.value,
                attempts=0,
                next_attempt_at=now,
                last_error=None,
            )
        )
        result = await self._session.execute(stmt)
        await self._session.flush()
        # len(fetchall()) вместо Result.rowcount — rowcount не типизирован
        # в SQLAlchemy stubs (mypy: "Result[Any]" has no attribute "rowcount")
        return bool(result.fetchall())

    async def get_by_id(self, message_id: str) -> OutboxMessage | None:
        """Получить запись outbox по идентификатору (без блокировки).

        Args:
            message_id: Идентификатор записи

        Returns:
            Запись или None, если она отсутствует
        """
        stmt = select(OutboxMessage).where(OutboxMessage.id == message_id)
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()

    async def count_by_status(self) -> dict[str, int]:
        """Подсчитать записи по статусам (для метрик/наблюдаемости).

        Returns:
            Словарь {статус: количество}
        """
        stmt = select(OutboxMessage.status, func.count()).group_by(OutboxMessage.status)
        result = await self._session.execute(stmt)
        return {str(row[0]): int(row[1]) for row in result.all()}

    async def count_ready(self) -> int:
        """Подсчитать pending-записи, готовые к отправке прямо сейчас.

        Учитывается backoff: считаются только записи с наступившим сроком
        следующей попытки (next_attempt_at <= now). Используется для
        наблюдаемости (heartbeat воркера, health-эндпоинт).

        Returns:
            Количество записей, ожидающих доставки в данный момент
        """
        now = datetime.now(UTC)
        stmt = (
            select(func.count())
            .select_from(OutboxMessage)
            .where(
                OutboxMessage.status == OutboxStatus.PENDING.value,
                OutboxMessage.next_attempt_at <= now,
            )
        )
        result = await self._session.execute(stmt)
        return int(result.scalar_one())
