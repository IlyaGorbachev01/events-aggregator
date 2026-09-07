import logging

from fastapi import APIRouter

from src.api.deps import ClientDep, SessionDep
from src.repositories.event import EventRepository
from src.repositories.ticket import TicketRepository
from src.schemas.api import (
    CancelTicketResponse,
    CreateTicketRequest,
    CreateTicketResponse,
)
from src.usecases.tickets import CancelTicketUsecase, CreateTicketUsecase

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/tickets", tags=["Tickets"])


@router.post("", response_model=CreateTicketResponse, status_code=201)
async def create_ticket(
    data: CreateTicketRequest,
    session: SessionDep,
    client: ClientDep,
) -> CreateTicketResponse:
    """Создание билета (регистрация на мероприятие)."""
    event_repo = EventRepository(session)
    ticket_repo = TicketRepository(session)
    usecase = CreateTicketUsecase(client, event_repo, ticket_repo)

    ticket_id = await usecase.execute(
        event_id=data.event_id,
        first_name=data.first_name,
        last_name=data.last_name,
        email=data.email,
        seat=data.seat,
    )
    await session.commit()
    return CreateTicketResponse(ticket_id=ticket_id)


@router.delete("/{ticket_id}", response_model=CancelTicketResponse)
async def cancel_ticket(
    ticket_id: str,
    session: SessionDep,
    client: ClientDep,
) -> CancelTicketResponse:
    """Отмена билета."""
    ticket_repo = TicketRepository(session)
    usecase = CancelTicketUsecase(client, ticket_repo)

    success = await usecase.execute(ticket_id)
    await session.commit()
    return CancelTicketResponse(success=success)
