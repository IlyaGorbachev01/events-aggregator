import logging
from datetime import datetime

import httpx

from src.core.enums import EventStatus
from src.core.exceptions import (
    EventNotFoundError,
    EventNotPublishedError,
    ProviderAuthError,
    ProviderUnavailableError,
    RegistrationDeadlineError,
    SeatNotAvailableError,
    TicketNotFoundError,
)
from src.repositories.event import EventRepository
from src.repositories.ticket import TicketRepository
from src.schemas.events_provider import RegisterRequest, UnregisterRequest
from src.services.events_provider_client import EventsProviderClient
from src.services.seats_cache import seats_cache
from src.usecases.seats import GetSeatsUsecase

logger = logging.getLogger(__name__)


class CreateTicketUsecase:
    """UseCase для создания билета."""

    def __init__(
        self,
        client: EventsProviderClient,
        events: EventRepository,
        tickets: TicketRepository,
    ) -> None:
        """Инициализация UseCase создания билета.

        Args:
            client: Клиент Events Provider API
            events: Репозиторий событий
            tickets: Репозиторий билетов
        """
        self._client = client
        self._events = events
        self._tickets = tickets

    async def execute(
        self,
        event_id: str,
        first_name: str,
        last_name: str,
        email: str,
        seat: str,
    ) -> str:
        """Создание билета с полной валидацией.

        Returns:
            ticket_id от провайдера
        """
        logger.info("Creating ticket for event %s, seat %s", event_id, seat)

        # Проверяем событие
        event = await self._events.get(event_id)
        if not event:
            raise EventNotFoundError(f"Event {event_id} not found")

        # Проверяем статус события
        if event.status != EventStatus.PUBLISHED:
            raise EventNotPublishedError(f"Event {event_id} is not published")

        # Проверяем дедлайн регистрации
        now = datetime.now().astimezone()
        if now > event.registration_deadline:
            raise RegistrationDeadlineError("Registration deadline has passed")

        # Проверяем доступность места через usecase (с кэшем)
        seats_usecase = GetSeatsUsecase(self._client, self._events)
        try:
            available_seats = await seats_usecase.execute(event_id)
        except (EventNotFoundError, EventNotPublishedError):
            raise
        except (ProviderUnavailableError, ProviderAuthError) as e:
            logger.error("Failed to check seat availability: %s", e)
            raise SeatNotAvailableError("Unable to verify seat availability") from e

        if seat not in available_seats:
            raise SeatNotAvailableError(f"Seat {seat} is not available")

        # Регистрируем в провайдере
        request = RegisterRequest(
            first_name=first_name,
            last_name=last_name,
            seat=seat,
            email=email,
        )

        try:
            response = await self._client.register(event_id, request)
        except httpx.HTTPStatusError as e:
            status_code = e.response.status_code
            if status_code == 401:
                raise ProviderAuthError("Provider authentication failed") from e
            if status_code >= 500:
                raise ProviderUnavailableError("Provider unavailable") from e
            raise

        ticket_id = response.ticket_id

        # 6. Сохраняем в своей БД
        await self._tickets.create(
            event_id=event_id,
            ticket_id=ticket_id,
            first_name=first_name,
            last_name=last_name,
            email=email,
            seat=seat,
        )

        # Инвалидируем кэш мест после регистрации
        seats_cache.invalidate(event_id)

        logger.info("Ticket created successfully: %s", ticket_id)
        return ticket_id


class CancelTicketUsecase:
    """UseCase для отмены билета."""

    def __init__(
        self,
        client: EventsProviderClient,
        tickets: TicketRepository,
    ) -> None:
        """Инициализация UseCase отмены билета.

        Args:
            client: Клиент Events Provider API
            tickets: Репозиторий билетов
        """
        self._client = client
        self._tickets = tickets

    async def execute(self, ticket_id: str) -> bool:
        """Отмена билета.

        Returns:
            True при успешной отмене
        """
        logger.info("Cancelling ticket %s", ticket_id)

        # 1. Получаем билет из своей БД
        ticket = await self._tickets.get_by_ticket_id(ticket_id)
        if not ticket:
            raise TicketNotFoundError(f"Ticket {ticket_id} not found")

        # 2. Отменяем регистрацию в провайдере
        request = UnregisterRequest(ticket_id=ticket_id)

        try:
            response = await self._client.unregister(ticket.event_id, request)
        except httpx.HTTPStatusError as e:
            status_code = e.response.status_code
            if status_code == 401:
                raise ProviderAuthError("Provider authentication failed") from e
            if status_code >= 500:
                raise ProviderUnavailableError("Provider unavailable") from e
            raise

        if response.success:
            # 3. Удаляем из своей БД
            await self._tickets.delete(ticket)
            # Инвалидируем кэш мест после отмены
            seats_cache.invalidate(ticket.event_id)
            logger.info("Ticket cancelled successfully: %s", ticket_id)

        return response.success
