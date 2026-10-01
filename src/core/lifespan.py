import asyncio
import contextlib
import logging
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from datetime import UTC, datetime

import sentry_sdk
from apscheduler.schedulers.asyncio import AsyncIOScheduler  # type: ignore
from fastapi import FastAPI

from src.core.config import settings
from src.core.database import async_session
from src.repositories.idempotency import IdempotencyRepository
from src.services.events_provider_client import EventsProviderClient
from src.services.outbox_worker import OutboxWorker
from src.services.sync_service import SyncService

logger = logging.getLogger(__name__)


async def scheduled_sync() -> None:
    """Задача для периодической синхронизации."""
    logger.info("Running scheduled sync task")

    async with async_session() as session:
        client = EventsProviderClient(
            base_url=settings.events_provider_base_url,
            api_key=settings.events_provider_api_key,
        )

        try:
            sync_service = SyncService(client, session)
            await sync_service.sync()
        finally:
            await client.close()


async def scheduled_cleanup() -> None:
    """Задача для периодической очистки протухших ключей идемпотентности."""
    logger.info("Running idempotency keys cleanup task")

    async with async_session() as session:
        repo = IdempotencyRepository(session)
        try:
            deleted = await repo.delete_expired()
            await session.commit()
            if deleted:
                logger.info("Removed %d expired idempotency keys", deleted)
        except Exception:
            await session.rollback()
            logger.exception("Idempotency keys cleanup failed")


@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncGenerator[None]:
    """Lifespan контекст для запуска фоновых задач."""
    logger.info("Starting application lifespan")

    # Создаем планировщик
    scheduler = AsyncIOScheduler()

    # Добавляем задачу синхронизации.
    # Первая синхронизация выполняется сразу после запуска планировщика
    # (next_run_time=now), периодические — по интервалу из конфига.
    # max_instances=1/coalesce=True — задачи не накладываются друг на друга.
    scheduler.add_job(
        scheduled_sync,
        "interval",
        minutes=settings.sync_interval_minutes,
        id="sync_events",
        name="Sync events from Events Provider API",
        replace_existing=True,
        coalesce=True,
        max_instances=1,
        next_run_time=datetime.now(UTC),
    )

    # Периодическая очистка протухших ключей идемпотентности (TTL)
    scheduler.add_job(
        scheduled_cleanup,
        "interval",
        hours=settings.idempotency_key_ttl_hours,
        id="cleanup_idempotency_keys",
        name="Remove expired idempotency keys",
        replace_existing=True,
        coalesce=True,
        max_instances=1,
    )

    # Запускаем планировщик
    scheduler.start()
    logger.info(
        "Scheduler started. Sync interval: %d minutes. Initial sync scheduled.",
        settings.sync_interval_minutes,
    )

    # Запускаем воркер outbox отдельной корутиной в том же процессе.
    # Воркер стартует сразу и не ждёт завершения первичной синхронизации.
    outbox_worker = OutboxWorker()
    worker_task = asyncio.create_task(outbox_worker.run())

    yield

    # Останавливаем планировщик и воркер при shutdown
    scheduler.shutdown(wait=False)
    logger.info("Scheduler stopped")

    outbox_worker.stop()
    worker_task.cancel()
    with contextlib.suppress(asyncio.CancelledError):
        await worker_task
    logger.info("Outbox worker task cancelled")

    # Flush Sentry (GlitchTip) — гарантируем отправку накопленных событий
    try:
        sentry_sdk.flush(timeout=5)
    except Exception:
        logger.exception("Sentry flush on shutdown failed")
