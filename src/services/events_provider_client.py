import httpx

from src.schemas.events_provider import (
    EventsListResponse,
    RegisterRequest,
    RegisterResponse,
    SeatsResponse,
    UnregisterRequest,
    UnregisterResponse,
)


class EventsProviderClient:
    """Клиент для работы с Events Provider API."""

    def __init__(self, base_url: str, api_key: str) -> None:
        """Инициализация клиента Events Provider API.

        Args:
            base_url: Базовый URL API
            api_key: API ключ для аутентификации
        """
        self._base_url = base_url.rstrip("/")
        self._api_key = api_key
        self._client = httpx.AsyncClient(
            base_url=self._base_url,
            headers={"x-api-key": api_key},
            timeout=30.0,
        )

    async def events(
        self, changed_at: str, cursor: str | None = None
    ) -> EventsListResponse:
        """Получение списка событий с поддержкой пагинации."""
        params = {"changed_at": changed_at}
        if cursor:
            params["cursor"] = cursor

        response = await self._client.get("/api/events/", params=params)
        response.raise_for_status()
        return EventsListResponse.model_validate(response.json())

    async def seats(self, event_id: str) -> SeatsResponse:
        """Получение списка свободных мест для события."""
        response = await self._client.get(f"/api/events/{event_id}/seats/")
        response.raise_for_status()
        return SeatsResponse.model_validate(response.json())

    async def register(
        self,
        event_id: str,
        request: RegisterRequest,
    ) -> RegisterResponse:
        """Регистрация участника на мероприятие."""
        response = await self._client.post(
            f"/api/events/{event_id}/register/",
            json=request.model_dump(),
        )
        response.raise_for_status()
        return RegisterResponse.model_validate(response.json())

    async def unregister(
        self,
        event_id: str,
        request: UnregisterRequest,
    ) -> UnregisterResponse:
        """Отмена регистрации участника."""
        response = await self._client.request(
            "DELETE",
            f"/api/events/{event_id}/unregister/",
            json=request.model_dump(),
        )
        response.raise_for_status()
        return UnregisterResponse.model_validate(response.json())

    async def close(self) -> None:
        """Закрытие HTTP клиента."""
        await self._client.aclose()
