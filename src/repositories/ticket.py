from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.models.ticket import Ticket


class TicketRepository:
    """Репозиторий для работы с билетами."""

    def __init__(self, session: AsyncSession) -> None:
        """Инициализация репозитория для работы с билетами."""
        self._session = session

    async def get_by_ticket_id(self, ticket_id: str) -> Ticket | None:
        """Получение билета по ticket_id от провайдера."""
        stmt = select(Ticket).where(Ticket.ticket_id == ticket_id)
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

    async def delete(self, ticket: Ticket) -> None:
        """Удаление билета."""
        stmt = delete(Ticket).where(Ticket.id == ticket.id)
        await self._session.execute(stmt)
        await self._session.flush()
