from datetime import datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.models.sync_metadata import SyncMetadata


class SyncMetadataRepository:
    """Репозиторий для работы с метаданными синхронизации."""

    def __init__(self, session: AsyncSession) -> None:
        """Инициализация репозитория для работы с метаданными синхронизации."""
        self._session = session

    async def get(self) -> SyncMetadata | None:
        """Получение последней записи метаданных."""
        stmt = select(SyncMetadata).order_by(SyncMetadata.id.desc()).limit(1)
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()

    async def upsert(
        self,
        last_sync_time: datetime,
        last_changed_at: datetime,
        sync_status: str,
    ) -> SyncMetadata:
        """Создание или обновление метаданных синхронизации."""
        metadata = await self.get()

        if metadata:
            metadata.last_sync_time = last_sync_time
            metadata.last_changed_at = last_changed_at
            metadata.sync_status = sync_status
        else:
            metadata = SyncMetadata(
                last_sync_time=last_sync_time,
                last_changed_at=last_changed_at,
                sync_status=sync_status,
            )
            self._session.add(metadata)

        await self._session.flush()
        return metadata
