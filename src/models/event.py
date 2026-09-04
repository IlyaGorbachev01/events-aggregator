from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy import ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.core.database import Base

if TYPE_CHECKING:
    from datetime import datetime

    from src.models import Place, Ticket


class Event(Base):
    """Событие / мероприятие."""

    __tablename__ = 'events'

    id: Mapped[str] = mapped_column(String, primary_key=True)
    name: Mapped[str] = mapped_column(String, nullable=False)
    place_id: Mapped[str] = mapped_column(ForeignKey('places.id'), nullable=False)
    event_time: Mapped[datetime] = mapped_column(nullable=False)
    registration_deadline: Mapped[datetime] = mapped_column(nullable=False)
    status: Mapped[str] = mapped_column(String, nullable=False)
    number_of_visitors: Mapped[int] = mapped_column(Integer, default=0)
    changed_at: Mapped[datetime] = mapped_column(nullable=False)
    created_at: Mapped[datetime] = mapped_column(nullable=False)
    status_changed_at: Mapped[datetime] = mapped_column(nullable=False)

    place: Mapped[Place] = relationship(back_populates='events')
    tickets: Mapped[list[Ticket]] = relationship(back_populates='event')
