from datetime import datetime

from fastapi import APIRouter, HTTPException, Query, Request

from src.api.deps import ClientDep, SessionDep
from src.core.exceptions import (
    EventNotFoundError,
    EventNotPublishedError,
    ProviderAuthError,
    ProviderUnavailableError,
)
from src.repositories.event import EventRepository
from src.schemas.api import (
    EventDetailSchema,
    EventSchema,
    PaginatedEventsResponse,
    SeatsResponse,
)
from src.usecases.seats import GetSeatsUsecase

router = APIRouter(prefix="/api/events", tags=["Events"])


@router.get("", response_model=PaginatedEventsResponse)
async def list_events(
    request: Request,
    session: SessionDep,
    date_from: str | None = Query(
        None, description="Фильтр по дате начала (YYYY-MM-DD)"
    ),
    page: int = Query(1, ge=1, description="Номер страницы"),
    page_size: int = Query(20, ge=1, le=100, description="Размер страницы"),
) -> PaginatedEventsResponse:
    """Получение списка событий с фильтрацией и пагинацией."""
    repo = EventRepository(session)

    # Парсинг даты
    date_from_dt = None
    if date_from:
        try:
            date_from_dt = datetime.fromisoformat(date_from)
        except ValueError:
            raise HTTPException(
                status_code=400, detail="Invalid date format. Use YYYY-MM-DD"
            ) from None

    # Получение данных
    offset = (page - 1) * page_size
    events, total = await repo.list(
        date_from=date_from_dt, offset=offset, limit=page_size
    )

    # Формирование URL для пагинации
    base_url = str(request.url).split("?")[0]
    next_url = None
    previous_url = None

    if page * page_size < total:
        next_url = f"{base_url}?page={page + 1}&page_size={page_size}"
        if date_from:
            next_url += f"&date_from={date_from}"

    if page > 1:
        previous_url = f"{base_url}?page={page - 1}&page_size={page_size}"
        if date_from:
            previous_url += f"&date_from={date_from}"

    # Преобразование в схемы с явной валидацией
    results = [EventSchema.model_validate(event) for event in events]

    return PaginatedEventsResponse(
        count=total,
        next=next_url,
        previous=previous_url,
        results=results,
    )


@router.get("/{event_id}", response_model=EventDetailSchema)
async def get_event(
    event_id: str,
    session: SessionDep,
) -> EventDetailSchema:
    """Получение детальной информации о событии."""
    repo = EventRepository(session)
    event = await repo.get(event_id)

    if not event:
        raise HTTPException(status_code=404, detail="Event not found")

    return EventDetailSchema.model_validate(event)


@router.get("/{event_id}/seats", response_model=SeatsResponse)
async def get_seats(
    event_id: str,
    session: SessionDep,
    client: ClientDep,
) -> SeatsResponse:
    """Получение списка свободных мест для события."""
    event_repo = EventRepository(session)
    usecase = GetSeatsUsecase(client, event_repo)

    try:
        available_seats = await usecase.execute(event_id)
    except EventNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e
    except EventNotPublishedError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    except ProviderUnavailableError as e:
        raise HTTPException(status_code=502, detail="Provider unavailable") from e
    except ProviderAuthError as e:
        raise HTTPException(
            status_code=500, detail="Provider authentication failed"
        ) from e

    return SeatsResponse(
        event_id=event_id,
        available_seats=available_seats,
    )
