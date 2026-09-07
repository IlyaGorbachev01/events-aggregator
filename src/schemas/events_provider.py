from datetime import datetime

from pydantic import BaseModel

from src.core.enums import EventStatus

# === Mixins ===


class TimestampMixin(BaseModel):
    """Миксин с базовыми временными метками."""

    changed_at: datetime
    created_at: datetime


# === Request Schemas ===


class RegisterRequest(BaseModel):
    """Схема запроса на регистрацию."""

    first_name: str
    last_name: str
    seat: str
    email: str


class UnregisterRequest(BaseModel):
    """Схема запроса на отмену регистрации."""

    ticket_id: str


# === Response Schemas ===


class PlaceResponse(TimestampMixin):
    """Схема ответа с информацией о площадке."""

    id: str
    name: str
    city: str
    address: str
    seats_pattern: str


class EventResponse(TimestampMixin):
    """Схема ответа с информацией о событии."""

    id: str
    name: str
    place: PlaceResponse
    event_time: datetime
    registration_deadline: datetime
    status: EventStatus
    number_of_visitors: int
    status_changed_at: datetime


class EventsListResponse(BaseModel):
    """Схема ответа со списком событий и пагинацией."""

    next: str | None
    previous: str | None
    results: list[EventResponse]


class SeatsResponse(BaseModel):
    """Схема ответа со списком свободных мест."""

    seats: list[str]


class RegisterResponse(BaseModel):
    """Схема ответа после успешной регистрации."""

    ticket_id: str


class UnregisterResponse(BaseModel):
    """Схема ответа после успешной отмены регистрации."""

    success: bool
