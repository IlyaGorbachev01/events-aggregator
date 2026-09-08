import logging

import httpx

from src.core.enums import EventStatus
from src.core.exceptions import (
    EventNotFoundError,
    EventNotPublishedError,
    ProviderAuthError,
    ProviderUnavailableError,
)
from src.repositories.event import EventRepository
from src.services.events_provider_client import EventsProviderClient
from src.services.seats_cache import seats_cache

logger = logging.getLogger(__name__)


class GetSeatsUsecase:
    """UseCase для получения списка свободных мест на мероприятии."""

    def __init__(
        self,
        client: EventsProviderClient,
        events: EventRepository,
    ) -> None:
        """Инициализирует кэш с ограничением по размеру и времени жизни записей."""
        self._client = client
        self._events = events

    async def execute(self, event_id: str) -> list[str]:
        """Возвращает список свободных мест для опубликованного события.

        Raises:
            EventNotFoundError: Событие не найдено в локальной БД.
            EventNotPublishedError: Событие не опубликовано.
            ProviderUnavailableError: Провайдер недоступен (5xx).
            ProviderAuthError: Ошибка аутентификации с провайдером.
        """
        logger.info("Fetching seats for event %s", event_id)

        event = await self._events.get(event_id)
        if not event:
            raise EventNotFoundError("Event %s not found", event_id)

        if event.status != EventStatus.PUBLISHED:
            raise EventNotPublishedError("Event %s is not published", event_id)

        # Проверяем глобальный кэш
        cached_seats = seats_cache.get(event_id)
        if cached_seats is not None:
            logger.info("Seats returned from cache for event %s", event_id)
            return cached_seats

        # Запрашиваем у провайдера с маппингом ошибок
        try:
            response = await self._client.seats(event_id)
            seats = response.seats
            seats_cache.set(event_id, seats)
            logger.info("Seats fetched from provider for event %s", event_id)
            return seats
        except httpx.HTTPStatusError as e:
            status_code = e.response.status_code
            if status_code == 404:
                logger.warning("Event %s not found in provider", event_id)
                raise EventNotFoundError(
                    "Event %s not found in provider", event_id
                ) from e
            if status_code == 401:
                logger.error("Provider authentication failed")
                raise ProviderAuthError("Provider authentication failed") from e
            if status_code >= 500:
                logger.error("Provider unavailable: %d", status_code)
                raise ProviderUnavailableError("Provider unavailable") from e

            logger.error("Unexpected provider error: %d", status_code)
            raise ProviderUnavailableError("Unexpected provider error") from e
