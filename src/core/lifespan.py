import asyncio
import contextlib
import logging
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from apscheduler.schedulers.asyncio import AsyncIOScheduler  # type: ignore
from fastapi import FastAPI

from src.core.config import settings
from src.core.database import async_session
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


@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncGenerator[None]:
    """Lifespan контекст для запуска фоновых задач."""
    logger.info("Starting application lifespan")

    # Создаем планировщик
    scheduler = AsyncIOScheduler()

    # Добавляем задачу синхронизации
    scheduler.add_job(
        scheduled_sync,
        "interval",
        minutes=settings.sync_interval_minutes,
        id="sync_events",
        name="Sync events from Events Provider API",
        replace_existing=True,
    )

    # Запускаем планировщик
    scheduler.start()
    logger.info(
        "Scheduler started. Sync interval: %d minutes",
        settings.sync_interval_minutes,
    )

    # Выполняем первичную синхронизацию при старте
    try:
        logger.info("Running initial sync on startup")
        await scheduled_sync()
    except Exception as e:
        logger.exception("Initial sync failed: %s", e)

    # Запускаем воркер outbox отдельной корутиной в том же процессе
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
