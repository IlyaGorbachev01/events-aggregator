from datetime import datetime

from sqlalchemy import DateTime, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from src.core.database import Base


class SyncMetadata(Base):
    """Метаданные последней синхронизации с Events Provider API."""

    __tablename__ = "sync_metadata"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    last_sync_time: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    last_changed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    sync_status: Mapped[str] = mapped_column(String, nullable=False)
