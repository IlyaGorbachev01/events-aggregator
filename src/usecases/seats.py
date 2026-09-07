import logging

from cachetools import TTLCache

from src.core.enums import EventStatus
from src.core.exceptions import EventNotFoundError, EventNotPublishedError
from src.repositories.event import EventRepository
from src.services.events_provider_client import EventsProviderClient

logger = logging.getLogger(__name__)


class GetSeatsUsecase:
    """UseCase для получения списка свободных мест на мероприятии."""

    def __init__(
        self,
        client: EventsProviderClient,
        events: EventRepository,
    ) -> None:
        """Инициализация UseCase для получения списка свободных мест на мероприятии."""
        self._client = client
        self._events = events
        self._cache: TTLCache = TTLCache(maxsize=100, ttl=30)

    async def execute(self, event_id: str) -> list[str]:
        """Возвращает список свободных мест для опубликованного события.

        Raises:
            EventNotFoundError: Событие не найдено в локальной БД.
            EventNotPublishedError: Событие не опубликовано.
        """
        logger.info("Fetching seats for event %s", event_id)

        event = await self._events.get(event_id)
        if not event:
            raise EventNotFoundError("Event %s not found", event_id)

        if event.status != EventStatus.PUBLISHED:
            raise EventNotPublishedError("Event %s is not published", event_id)

        if event_id not in self._cache:
            response = await self._client.seats(event_id)
            self._cache[event_id] = response.seats
            logger.info("Seats fetched from provider for event %s", event_id)
        else:
            logger.info("Seats returned from cache for event %s", event_id)

        return self._cache[event_id]
