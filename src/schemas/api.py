from datetime import datetime

from pydantic import BaseModel, ConfigDict, EmailStr, Field

from src.core.enums import EventStatus


class PlaceSchema(BaseModel):
    """Схема площадки для API ответов."""

    model_config = ConfigDict(from_attributes=True)

    id: str
    name: str
    city: str
    address: str


class PlaceDetailSchema(PlaceSchema):
    """Детальная схема площадки с seats_pattern."""

    seats_pattern: str


class EventSchema(BaseModel):
    """Схема события для API ответов."""

    model_config = ConfigDict(from_attributes=True)

    id: str
    name: str
    place: PlaceSchema
    event_time: datetime
    registration_deadline: datetime
    status: EventStatus
    number_of_visitors: int


class EventDetailSchema(EventSchema):
    """Детальная схема события с seats_pattern."""

    place: PlaceDetailSchema


class PaginatedEventsResponse(BaseModel):
    """Схема пагинированного ответа со списком событий."""

    count: int
    next: str | None
    previous: str | None
    results: list[EventSchema]


class SeatsResponse(BaseModel):
    """Схема ответа со списком свободных мест."""

    event_id: str
    available_seats: list[str]


class CreateTicketRequest(BaseModel):
    """Схема запроса на создание билета.

    Поле `idempotency_key` — необязательный ключ идемпотентности
    (строка 8–128 символов). Передаётся клиентом в теле запроса; при
    повторной отправке того же запроса с тем же ключом возвращается тот
    же билет без повторной регистрации у провайдера. Тот же ключ с
    другими данными -> HTTP 409 Conflict.
    """

    event_id: str
    first_name: str
    last_name: str
    email: EmailStr
    seat: str
    idempotency_key: str | None = Field(
        default=None,
        min_length=8,
        max_length=128,
        pattern=r"^[\w\-:.]+$",
        description=(
            "Ключ идемпотентности операции. Повтор запроса с тем же ключом "
            "и теми же данными возвращает тот же ticket_id (201); "
            "тот же ключ, но другие данные — 409 Conflict."
        ),
    )


class CreateTicketResponse(BaseModel):
    """Схема ответа после создания билета."""

    ticket_id: str


class CancelTicketResponse(BaseModel):
    """Схема ответа после отмены билета."""

    success: bool
