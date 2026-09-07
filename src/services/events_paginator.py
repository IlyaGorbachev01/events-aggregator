from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from src.schemas.events_provider import EventResponse
    from src.services.events_provider_client import EventsProviderClient


class EventsPaginator:
    """Асинхронный итератор для обхода всех страниц событий Events Provider API."""

    def __init__(
        self,
        client: EventsProviderClient,
        changed_at: str = "2020-01-01",
    ) -> None:
        """Инициализация пагинатора.

        Args:
            client: Клиент для работы с Events Provider API
            changed_at: Дата в формате YYYY-MM-DD для фильтрации событий
        """
        self._client = client
        self._changed_at = changed_at
        self._cursor: str | None = None
        self._buffer: list[EventResponse] = []
        self._exhausted = False

    def __aiter__(self) -> EventsPaginator:
        """Возвращает итератор для асинхронной итерации.

        Returns:
            Экземпляр EventsPaginator
        """
        return self

    async def __anext__(self) -> EventResponse:
        """Возвращает следующее событие из пагинации."""
        while not self._exhausted:
            if self._buffer:
                return self._buffer.pop(0)

            data = await self._client.events(self._changed_at, self._cursor)
            self._buffer.extend(data.results)

            next_url = data.next
            if next_url:
                self._cursor = self._extract_cursor_from_url(next_url)
            else:
                self._exhausted = True

        if not self._buffer:
            raise StopAsyncIteration

        return self._buffer.pop(0)

    @staticmethod
    def _extract_cursor_from_url(url: str) -> str | None:
        """Извлекает курсор из URL следующей страницы."""
        from urllib.parse import parse_qs, urlparse

        parsed = urlparse(url)
        params = parse_qs(parsed.query)
        cursor_list = params.get("cursor")
        return cursor_list[0] if cursor_list else None
