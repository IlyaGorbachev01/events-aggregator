"""Воркер transactional outbox.

Периодически читает неотправленные записи из таблицы outbox и выполняет
доставку событий (отправку уведомлений в Capashino). Запуск — отдельной
корутиной в lifespan FastAPI, в том же процессе.

Гарантии доставки:
- Каждое сообщение обрабатывается в собственной короткой транзакции:
  выборка id пачки -> повторная блокировка записи (FOR UPDATE SKIP LOCKED)
  -> отправка во внешний сервис -> коммит нового статуса. Ошибка на одном
  сообщении не откатывает статусы уже успешно доставленных сообщений пачки.
- Блокировка строки удерживается только на время HTTP-вызова этого
  сообщения; соседние записи пачки блокировок не держат.
- Успешный ответ Capashino (201 или 409 по idempotency_key) — единственный
  случай, когда запись помечается sent. При сетевой ошибке/5xx запись
  остаётся pending с экспоненциальным backoff; после превышения лимита
  попыток переводится в failed с сохранением текста последней ошибки.
"""

import asyncio
import contextlib
import logging
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from src.core.config import settings
from src.core.database import async_session as async_session_factory
from src.core.enums import NotificationOutcome, OutboxEventType, OutboxStatus
from src.repositories.outbox import OutboxRepository
from src.services.notification_client import (
    NotificationClient,
    NotificationDeliveryError,
    NotificationPermanentError,
)

logger = logging.getLogger(__name__)


class OutboxWorker:
    """Фоновый воркер доставки событий из outbox."""

    def __init__(
        self,
        notifier: NotificationClient | None = None,
        session_factory: async_sessionmaker[AsyncSession] | None = None,
    ) -> None:
        """Инициализация воркера с параметрами из конфигурации.

        Args:
            notifier: Клиент уведомлений (для тестов; по умолчанию
                      создаётся из настроек Capashino)
            session_factory: Фабрика сессий (для тестов; по умолчанию
                             используется глобальная async_session)
        """
        self._poll_interval = settings.outbox_poll_interval_seconds
        self._batch_size = settings.outbox_batch_size
        self._max_attempts = settings.outbox_max_attempts
        self._backoff_base = settings.outbox_backoff_base_seconds
        self._backoff_max = settings.outbox_backoff_max_seconds
        self._backoff_jitter = settings.outbox_backoff_jitter_ratio
        self._stop_event = asyncio.Event()
        self._session_factory = session_factory or async_session_factory
        if notifier is not None:
            self._notifier = notifier
            self._owns_notifier = False
        else:
            self._notifier = NotificationClient(
                base_url=settings.capashino_base_url,
                api_key=settings.capashino_api_key,
                timeout=settings.capashino_timeout_seconds,
            )
            self._owns_notifier = True

    async def run(self) -> None:
        """Основной цикл воркера: опрос outbox по интервалу."""
        logger.info(
            (
                "Outbox worker started (interval=%.1fs, batch=%d, "
                "max_attempts=%d, backoff=%.1f..%.1fs)"
            ),
            self._poll_interval,
            self._batch_size,
            self._max_attempts,
            self._backoff_base,
            self._backoff_max,
        )
        if self._owns_notifier and not settings.capashino_api_key:
            logger.warning(
                "CAPASHINO_API_KEY is not configured: notification delivery "
                "will fail with HTTP 401 until the key is provided"
            )
        try:
            while not self._stop_event.is_set():
                try:
                    processed = await self.process_once()
                    if processed:
                        pending_total = await self.count_ready()
                        # Heartbeat: видно, что воркер живёт и сколько
                        # событий ещё ожидает доставки (между ошибками в
                        # логах иначе тишина).
                        logger.info(
                            "Outbox iteration done: attempted=%d, pending_left=%d",
                            processed,
                            pending_total,
                        )
                except asyncio.CancelledError:
                    raise
                except Exception:
                    logger.exception("Outbox worker iteration failed")
                with contextlib.suppress(TimeoutError):
                    await asyncio.wait_for(
                        self._stop_event.wait(),
                        timeout=self._poll_interval,
                    )
        finally:
            if self._owns_notifier:
                await self._notifier.close()

        logger.info("Outbox worker stopped")

    def stop(self) -> None:
        """Остановить воркер после текущей итерации."""
        self._stop_event.set()

    async def process_once(self) -> int:
        """Обработать одну пачку записей, готовых к отправке.

        Сначала выбираются id записей (короткая транзакция с блокировкой),
        затем каждое сообщение доставляется в отдельной транзакции —
        чтобы ошибка одной записи не откатывала результаты других.

        Returns:
            Количество записей, по которым была выполнена попытка доставки
        """
        message_ids = await self._claim_batch()
        processed = 0
        for message_id in message_ids:
            if await self._process_message(message_id):
                processed += 1
        return processed

    async def count_ready(self) -> int:
        """Подсчитать записи, готовые к отправке сейчас (для heartbeat/метриок).

        Возвращает полный срез очереди: суммирует pending-записи независимо
        от того, наступил ли срок их следующей попытки (backoff) —
        т.е. все ещё не доставленные события.

        Returns:
            Количество ожидающих доставки записей (pending)
        """
        async with self._session_factory() as session:
            repo = OutboxRepository(session)
            counts = await repo.count_by_status()
            ready_now = await repo.count_ready()
        total_pending = counts.get(OutboxStatus.PENDING.value, 0)
        deferred = max(total_pending - ready_now, 0)
        # Полный срез очереди в debug-логе: всего pending / из них готовы
        # (срок наступил) / в backoff / доставлено / исчерпано попытки
        logger.debug(
            "Outbox backlog: pending=%d (ready_now=%d, in_backoff=%d), "
            "sent=%d, failed=%d",
            total_pending,
            ready_now,
            deferred,
            counts.get(OutboxStatus.SENT.value, 0),
            counts.get(OutboxStatus.FAILED.value, 0),
        )
        return total_pending

    async def requeue_failed(self, message_id: str) -> bool:
        """Вернуть failed-запись в очередь (ручной re-drive).

        Применяется после инцидента с Capashino: события, исчерпавшие лимит
        попыток, иначе остались бы недоставленными навсегда.

        Args:
            message_id: Идентификатор записи outbox

        Returns:
            True, если запись была в failed и переведена в pending
        """
        async with self._session_factory() as session:
            repo = OutboxRepository(session)
            requeued = await repo.requeue_failed(message_id)
            await session.commit()
        if requeued:
            logger.info("Outbox message %s re-queued from failed", message_id)
        else:
            logger.warning(
                "Outbox message %s not found in failed status, nothing to requeue",
                message_id,
            )
        return requeued

    async def _claim_batch(self) -> list[str]:
        """Выбрать пачку pending-записей и зафиксировать их id.

        Транзакция завершается сразу после выборки: блокировки строк
        освобождаются, а на время HTTP-вызовов захватывается отдельная
        блокировка на каждую обрабатываемую запись (в _process_message).

        Returns:
            Список идентификаторов записей для обработки
        """
        async with self._session_factory() as session:
            repo = OutboxRepository(session)
            messages = await repo.fetch_pending(limit=self._batch_size)
            ids = [message.id for message in messages]
            # Откат вместо коммита: выборка с FOR UPDATE ничего не меняет,
            # а блокировки освобождаются немедленно по окончании сессии.
            await session.rollback()
        return ids

    async def _process_message(self, message_id: str) -> bool:
        """Доставить одну запись outbox в собственной транзакции.

        Returns:
            True, если по записи была выполнена попытка доставки;
            False, если запись пропущена (уже обработана или заблокирована
            другим экземпляром воркера)
        """
        async with self._session_factory() as session:
            repo = OutboxRepository(session)
            # Повторно фиксируем запись с блокировкой: если её успел забрать
            # другой экземпляр воркера (SKIP LOCKED) — пропускаем обработку.
            message = await repo.get_for_update(message_id)
            if message is None or message.status != OutboxStatus.PENDING:
                await session.rollback()
                return False

            outcome, error = await self._deliver(message.payload, message.id)

            if outcome in (
                NotificationOutcome.SENT,
                NotificationOutcome.IDEMPOTENT_DUPLICATE,
            ):
                await repo.mark_sent(message.id)
                await session.commit()
                logger.info(
                    "Outbox message %s delivered (outcome=%s)",
                    message.id,
                    outcome,
                )
                return True

            attempts_before = message.attempts
            exhausted = await repo.register_retry(
                message,
                error or "unknown error",
                max_attempts=self._max_attempts,
                backoff_base_seconds=self._backoff_base,
                backoff_max_seconds=self._backoff_max,
                backoff_jitter_ratio=self._backoff_jitter,
            )
            await session.commit()
            if exhausted:
                logger.error(
                    "Outbox message %s exceeded max attempts (%d), marked as "
                    "failed. Last error: %s. Requeue via "
                    "POST /api/outbox/%s/requeue after fixing the cause.",
                    message.id,
                    self._max_attempts,
                    error,
                    message.id,
                )
            else:
                logger.warning(
                    "Outbox message %s delivery failed (attempt %d/%d, "
                    "outcome=%s), will retry. Error: %s",
                    message.id,
                    attempts_before + 1,
                    self._max_attempts,
                    outcome,
                    error,
                )
            return True

    async def _deliver(
        self,
        payload: dict[str, Any],
        message_id: str,
    ) -> tuple[NotificationOutcome, str | None]:
        """Выполнить доставку одного события во внешний сервис.

        Для события ticket_purchased отправляет уведомление в Capashino.
        idempotency_key стабилен и привязан к id записи outbox, поэтому
        повторная обработка той же записи не создаёт дубликат уведомления.

        Args:
            payload: Данные события из записи outbox
            message_id: Идентификатор записи outbox

        Returns:
            Кортеж (результат попытки, текст ошибки или None)
        """
        event_type = payload.get("event_type", "unknown")
        if event_type == OutboxEventType.TICKET_PURCHASED:
            return await self._send_ticket_notification(payload, message_id)

        # Неизвестный тип события — повторная обработка не поможет.
        logger.error(
            "Unknown outbox event type %r in message %s",
            event_type,
            message_id,
        )
        return NotificationOutcome.PERMANENT, f"unsupported event_type: {event_type}"

    async def _send_ticket_notification(
        self,
        payload: dict[str, Any],
        message_id: str,
    ) -> tuple[NotificationOutcome, str | None]:
        """Отправить уведомление о покупке билета в Capashino."""
        ticket_id = payload.get("ticket_id")
        message_text = payload.get("message")
        if not ticket_id or not message_text or not str(message_text).strip():
            # Некорректный payload — данные не изменятся при повторе.
            return (
                NotificationOutcome.PERMANENT,
                "payload missing ticket_id or non-empty message",
            )

        try:
            outcome = await self._notifier.send_notification(
                message=str(message_text),
                reference_id=str(ticket_id),
                idempotency_key=f"outbox:{message_id}",
            )
        except NotificationDeliveryError as exc:
            return NotificationOutcome.RETRYABLE, str(exc)
        except NotificationPermanentError as exc:
            return NotificationOutcome.PERMANENT, str(exc)
        return outcome, None
