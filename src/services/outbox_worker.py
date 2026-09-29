"""Воркер transactional outbox.

Периодически читает неотправленные записи из таблицы outbox и выполняет
их обработку. Запуск — отдельной корутиной в lifespan
FastAPI, в том же процессе.
"""

import asyncio
import contextlib
import logging

from src.core.config import settings
from src.core.database import async_session
from src.repositories.outbox import OutboxRepository

logger = logging.getLogger(__name__)


class OutboxWorker:
    """Фоновый воркер доставки событий из outbox."""

    def __init__(self) -> None:
        """Инициализация воркера с параметрами из конфигурации."""
        self._poll_interval = settings.outbox_poll_interval_seconds
        self._batch_size = settings.outbox_batch_size
        self._max_attempts = settings.outbox_max_attempts
        self._stop_event = asyncio.Event()

    async def run(self) -> None:
        """Основной цикл воркера: опрос outbox по интервалу."""
        logger.info(
            "Outbox worker started (interval=%.1fs, batch=%d, max_attempts=%d)",
            self._poll_interval,
            self._batch_size,
            self._max_attempts,
        )
        while not self._stop_event.is_set():
            try:
                await self.process_once()
            except asyncio.CancelledError:
                raise
            except Exception:
                logger.exception("Outbox worker iteration failed")
            with contextlib.suppress(TimeoutError):
                await asyncio.wait_for(
                    self._stop_event.wait(),
                    timeout=self._poll_interval,
                )
        logger.info("Outbox worker stopped")

    def stop(self) -> None:
        """Остановить воркер после текущей итерации."""
        self._stop_event.set()

    async def process_once(self) -> int:
        """Обработать одну пачку pending-записей.

        Returns:
            Количество обработанных записей
        """
        processed = 0
        async with async_session() as session:
            repo = OutboxRepository(session)
            messages = await repo.fetch_pending(limit=self._batch_size)
            if not messages:
                return 0

            for message in messages:
                try:
                    await self._handle_message(message.payload, message.id)
                except Exception as exc:
                    logger.error(
                        "Failed to deliver outbox message %s (attempt %d): %s",
                        message.id,
                        message.attempts + 1,
                        exc,
                    )
                    await repo.increment_attempts(message.id)
                    if message.attempts + 1 >= self._max_attempts:
                        logger.error(
                            "Outbox message %s exceeded max attempts (%d), "
                            "marking as failed",
                            message.id,
                            self._max_attempts,
                        )
                        await repo.mark_failed(message.id)
                    else:
                        # Откатываем блокировку, запись останется pending
                        continue
                else:
                    await repo.mark_sent(message.id)
                processed += 1

            await session.commit()
        return processed

    async def _handle_message(self, payload: dict, message_id: str) -> None:
        """Доставка одной записи outbox.

        Заглушка-логгер; позже реализовать вызов Capashino API.

        Args:
            payload: Данные события
            message_id: Идентификатор записи outbox
        """
        event_type = payload.get("event_type", "unknown")
        logger.info("Delivering outbox message %s (type=%s)", message_id, event_type)
