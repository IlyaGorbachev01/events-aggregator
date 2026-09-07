import logging
from datetime import datetime

from cachetools import TTLCache

from src.core.exceptions import (
    EventNotFoundError,
    EventNotPublishedError,
    RegistrationDeadlineError,
    SeatNotAvailableError,
    TicketNotFoundError,
)
from src.repositories.event import EventRepository
from src.repositories.ticket import TicketRepository
from src.schemas.events_provider import RegisterRequest, UnregisterRequest
from src.services.events_provider_client import EventsProviderClient

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
        self._seats_cache: TTLCache = TTLCache(maxsize=100, ttl=30)

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

        # 1. Проверяем событие
        event = await self._events.get(event_id)
        if not event:
            raise EventNotFoundError(f"Event {event_id} not found")

        # 2. Проверяем статус события
        if event.status != "published":
            raise EventNotPublishedError(f"Event {event_id} is not published")

        # 3. Проверяем дедлайн регистрации
        now = datetime.now().astimezone()
        if now > event.registration_deadline:
            raise RegistrationDeadlineError("Registration deadline has passed")

        # 4. Проверяем доступность места (с кэшированием)
        available_seats = await self._get_available_seats(event_id)
        if seat not in available_seats:
            raise SeatNotAvailableError(f"Seat {seat} is not available")

        # 5. Регистрируем в провайдере
        request = RegisterRequest(
            first_name=first_name,
            last_name=last_name,
            seat=seat,
            email=email,
        )
        response = await self._client.register(event_id, request)
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

        logger.info("Ticket created successfully: %s", ticket_id)
        return ticket_id

    async def _get_available_seats(self, event_id: str) -> list[str]:
        """Получение списка свободных мест с кэшированием."""
        if event_id not in self._seats_cache:
            response = await self._client.seats(event_id)
            self._seats_cache[event_id] = response.seats

        return self._seats_cache[event_id]


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
        response = await self._client.unregister(ticket.event_id, request)

        if response.success:
            # 3. Удаляем из своей БД
            await self._tickets.delete(ticket)
            logger.info("Ticket cancelled successfully: %s", ticket_id)

        return response.success
