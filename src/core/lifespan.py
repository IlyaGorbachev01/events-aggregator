import logging
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from apscheduler.schedulers.asyncio import AsyncIOScheduler  # type: ignore
from fastapi import FastAPI

from src.core.config import settings
from src.core.database import async_session
from src.services.events_provider_client import EventsProviderClient
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
        "Scheduler started. Sync interval: %d minutes", settings.sync_interval_minutes
    )

    # Выполняем первичную синхронизацию при старте
    try:
        logger.info("Running initial sync on startup")
        await scheduled_sync()
    except Exception as e:
        logger.exception("Initial sync failed: %s", e)

    yield

    # Останавливаем планировщик при shutdown
    scheduler.shutdown(wait=False)
    logger.info("Scheduler stopped")
