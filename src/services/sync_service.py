import logging
from datetime import UTC, datetime

from sqlalchemy.ext.asyncio import AsyncSession

from src.repositories.event import EventRepository
from src.repositories.place import PlaceRepository
from src.repositories.sync import SyncMetadataRepository
from src.services.events_paginator import EventsPaginator
from src.services.events_provider_client import EventsProviderClient

logger = logging.getLogger(__name__)

# Дата-«заглушка» для метаданных при первой синхронизации: заведомо в прошлом,
# чтобы следующая синхронизация снова захватила все события (changed_at=X
# означает «изменённые начиная с X», включая сам день X).
_EPOCH = datetime(2020, 1, 1, tzinfo=UTC)


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
        """Выполнение синхронизации событий.

        metadata создаётся сразу (со статусом running), чтобы запись о
        последней попытке синхронизации существовала даже при первом запуске
        и при ошибках. По завершении статус обновляется на success/failed.
        """
        logger.info("Starting events sync")

        # Получаем last_changed_at из метаданных
        metadata = await self._sync_repo.get()
        changed_at = "2020-01-01"
        if metadata:
            changed_at = metadata.last_changed_at.strftime("%Y-%m-%d")

        # Фиксируем начало синхронизации (гарантирует наличие записи metadata)
        try:
            metadata = await self._sync_repo.upsert(
                last_sync_time=datetime.now(UTC),
                last_changed_at=metadata.last_changed_at if metadata else _EPOCH,
                sync_status="running",
            )
            await self._session.commit()
        except Exception:
            await self._session.rollback()
            logger.exception("Failed to save sync metadata (start)")

        logger.info("Syncing events changed after %s", changed_at)

        try:
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

            # Обновляем метаданные синхронизации.
            # При пустом результате last_changed_at не двигаем вперёд —
            # иначе одна пустая/неудачная итерация навсегда «съест» события.
            await self._sync_repo.upsert(
                last_sync_time=datetime.now(UTC),
                last_changed_at=max_changed_at
                if max_changed_at
                else (metadata.last_changed_at if metadata else _EPOCH),
                sync_status="success",
            )
            await self._session.commit()

            logger.info(
                "Sync completed successfully. Processed %d events",
                events_count,
            )

        except Exception as e:
            logger.exception("Sync failed: %s", e)
            await self._session.rollback()

            # Сохраняем статус ошибки
            try:
                await self._sync_repo.upsert(
                    last_sync_time=datetime.now(UTC),
                    last_changed_at=metadata.last_changed_at if metadata else _EPOCH,
                    sync_status="failed",
                )
                await self._session.commit()
            except Exception as meta_error:
                logger.error("Failed to save sync metadata: %s", meta_error)

            raise
