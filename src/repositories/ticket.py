from datetime import UTC, datetime

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.enums import TicketStatus
from src.models.ticket import Ticket


class TicketRepository:
    """Репозиторий для работы с билетами."""

    def __init__(self, session: AsyncSession) -> None:
        """Инициализация репозитория для работы с билетами."""
        self._session = session

    @property
    def session(self) -> AsyncSession:
        """БД-сессия репозитория (для управления транзакцией в usecase)."""
        return self._session

    async def get_by_ticket_id(self, ticket_id: str) -> Ticket | None:
        """Получение активного билета по ticket_id от провайдера.

        Отменённые билеты (status=CANCELLED) не возвращаются — для
        внешних слоёв они неотличимы от удалённых.
        """
        stmt = select(Ticket).where(
            Ticket.ticket_id == ticket_id, Ticket.status == TicketStatus.ACTIVE
        )
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()

    async def create(
        self,
        event_id: str,
        ticket_id: str,
        first_name: str,
        last_name: str,
        email: str,
        seat: str,
    ) -> Ticket:
        """Создание новой регистрации."""
        ticket = Ticket(
            event_id=event_id,
            ticket_id=ticket_id,
            first_name=first_name,
            last_name=last_name,
            email=email,
            seat=seat,
        )
        self._session.add(ticket)
        await self._session.flush()
        return ticket

    async def cancel(self, ticket: Ticket) -> None:
        """Мягкая отмена билета: статус CANCELLED и отметка времени."""
        stmt = (
            update(Ticket)
            .where(Ticket.id == ticket.id)
            .values(status=TicketStatus.CANCELLED, cancelled_at=datetime.now(UTC))
        )
        await self._session.execute(stmt)
        await self._session.flush()

    async def count_active(self) -> int:
        """Количество активных (не отменённых) билетов."""
        stmt = (
            select(func.count())
            .select_from(Ticket)
            .where(Ticket.status == TicketStatus.ACTIVE)
        )
        result = await self._session.execute(stmt)
        return result.scalar() or 0

    async def count_cancelled(self) -> int:
        """Количество отменённых билетов."""
        stmt = (
            select(func.count())
            .select_from(Ticket)
            .where(Ticket.status == TicketStatus.CANCELLED)
        )
        result = await self._session.execute(stmt)
        return result.scalar() or 0
