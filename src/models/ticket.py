from __future__ import annotations

from datetime import UTC, datetime
from typing import TYPE_CHECKING
from uuid import uuid4

from sqlalchemy import ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.core.database import Base

if TYPE_CHECKING:
    from src.models import Event


class Ticket(Base):
    """Регистрация участника на мероприятие."""

    __tablename__ = "tickets"

    id: Mapped[str] = mapped_column(
        String, primary_key=True, default=lambda: str(uuid4())
    )
    event_id: Mapped[str] = mapped_column(ForeignKey("events.id"), nullable=False)
    ticket_id: Mapped[str] = mapped_column(String, unique=True, nullable=False)
    first_name: Mapped[str] = mapped_column(String, nullable=False)
    last_name: Mapped[str] = mapped_column(String, nullable=False)
    email: Mapped[str] = mapped_column(String, nullable=False)
    seat: Mapped[str] = mapped_column(String, nullable=False)
    created_at: Mapped[datetime] = mapped_column(default=datetime.now(UTC))

    event: Mapped[Event] = relationship(back_populates="tickets")
