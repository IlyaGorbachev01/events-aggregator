import logging

from fastapi import APIRouter, HTTPException

from src.api.deps import ClientDep, SessionDep
from src.core.exceptions import (
    EventNotFoundError,
    EventNotPublishedError,
    RegistrationDeadlineError,
    SeatNotAvailableError,
    TicketNotFoundError,
)
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

    try:
        ticket_id = await usecase.execute(
            event_id=data.event_id,
            first_name=data.first_name,
            last_name=data.last_name,
            email=data.email,
            seat=data.seat,
        )
        return CreateTicketResponse(ticket_id=ticket_id)

    except EventNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e
    except EventNotPublishedError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    except RegistrationDeadlineError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    except SeatNotAvailableError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    except Exception as e:
        logger.error(f"Failed to create ticket: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Internal server error") from e


@router.delete("/{ticket_id}", response_model=CancelTicketResponse)
async def cancel_ticket(
    ticket_id: str,
    session: SessionDep,
    client: ClientDep,
) -> CancelTicketResponse:
    """Отмена билета."""
    ticket_repo = TicketRepository(session)
    usecase = CancelTicketUsecase(client, ticket_repo)

    try:
        success = await usecase.execute(ticket_id)
        return CancelTicketResponse(success=success)

    except TicketNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e
    except Exception as e:
        logger.error(f"Failed to cancel ticket: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Internal server error") from e
