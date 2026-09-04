import logging
from datetime import datetime

from sqlalchemy.ext.asyncio import AsyncSession

from src.repositories.event import EventRepository
from src.repositories.place import PlaceRepository
from src.repositories.sync import SyncMetadataRepository
from src.services.events_paginator import EventsPaginator
from src.services.events_provider_client import EventsProviderClient

logger = logging.getLogger(__name__)


class SyncService:
    """Сервис для синхронизации событий с Events Provider API."""

    def __init__(
        self,
        client: EventsProviderClient,
        session: AsyncSession,
    ) -> None:
        """Инициализация сервиса для синхронизации событий с Events Provider API."""
        self._client = client
        self._session = session
        self._event_repo = EventRepository(session)
        self._place_repo = PlaceRepository(session)
        self._sync_repo = SyncMetadataRepository(session)

    async def sync(self) -> None:
        """Выполнение синхронизации событий."""
        logger.info("Starting events sync")

        try:
            # Получаем last_changed_at из метаданных
            metadata = await self._sync_repo.get()
            changed_at = "2026-01-01"
            if metadata:
                changed_at = metadata.last_changed_at.strftime("%Y-%m-%d")

            logger.info(f"Syncing events changed after {changed_at}")

            # Создаем пагинатор
            paginator = EventsPaginator(self._client, changed_at)

            max_changed_at = None
            events_count = 0

            # Обходим все страницы
            async for event_data in paginator:
                # Upsert place
                place = await self._place_repo.upsert(event_data.place)

                # Upsert event
                await self._event_repo.upsert(event_data, place.id)

                # Отслеживаем максимальное changed_at
                if max_changed_at is None or event_data.changed_at > max_changed_at:
                    max_changed_at = event_data.changed_at

                events_count += 1

            # Коммитим все изменения
            await self._session.commit()

            # Обновляем метаданные синхронизации
            if max_changed_at:
                await self._sync_repo.upsert(
                    last_sync_time=datetime.utcnow(),
                    last_changed_at=max_changed_at,
                    sync_status="success",
                )
                await self._session.commit()

            logger.info(f"Sync completed successfully. Processed {events_count} events")

        except Exception as e:
            logger.error(f"Sync failed: {e}", exc_info=True)
            await self._session.rollback()

            # Сохраняем статус ошибки
            try:
                await self._sync_repo.upsert(
                    last_sync_time=datetime.utcnow(),
                    last_changed_at=metadata.last_changed_at
                    if metadata
                    else datetime(2026, 1, 1),
                    sync_status="failed",
                )
                await self._session.commit()
            except Exception as meta_error:
                logger.error(f"Failed to save sync metadata: {meta_error}")

            raise
