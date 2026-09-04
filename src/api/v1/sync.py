import logging

from fastapi import APIRouter, BackgroundTasks

from src.core.config import settings
from src.core.database import async_session
from src.services.events_provider_client import EventsProviderClient
from src.services.sync_service import SyncService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/sync", tags=["Sync"])


async def run_sync_task() -> None:
    """Фоновая задача для запуска синхронизации."""
    async with async_session() as session:
        client = EventsProviderClient(
            base_url=settings.events_provider_base_url,
            api_key=settings.events_provider_api_key,
        )

        try:
            sync_service = SyncService(client, session)
            await sync_service.sync()
        except Exception as e:
            logger.error(f"Manual sync failed: {e}", exc_info=True)
        finally:
            await client.close()


@router.post("/trigger")
async def trigger_sync(background_tasks: BackgroundTasks) -> dict[str, str]:
    """Ручной запуск синхронизации в фоновом режиме."""
    logger.info("Manual sync triggered")
    background_tasks.add_task(run_sync_task)
    return {"status": "sync started"}
