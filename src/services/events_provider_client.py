import logging
import time

import httpx
from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from src.core.metrics import (
    events_provider_request_duration_seconds,
    events_provider_requests_total,
)
from src.schemas.events_provider import (
    EventsListResponse,
    RegisterRequest,
    RegisterResponse,
    SeatsResponse,
    UnregisterRequest,
    UnregisterResponse,
)

logger = logging.getLogger(__name__)


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
            follow_redirects=True,
        )

    async def _request(
        self,
        method: str,
        url: str,
        *,
        endpoint: str,
        params: dict[str, str] | None = None,
        json: dict | None = None,
    ) -> httpx.Response:
        """Выполнить запрос к провайдеру с проверкой статуса и сбором метрик.

        Метрики пишутся на каждом физическом HTTP-обращении, включая
        повторы tenacity — так отражается реальная сетевая нагрузка.
        Ошибки сети/таймауты фиксируются со status="error".

        Args:
            method: HTTP-метод запроса.
            url: Путь запроса относительно base_url.
            endpoint: Лейбл эндпоинта для метрик (/events, /seats, /registration).
            params: Query-параметры.
            json: Тело запроса (JSON).

        Returns:
            HTTP-ответ провайдера.

        Raises:
            httpx.HTTPStatusError: Если провайдер вернул 4xx/5xx.
        """
        start = time.monotonic()
        status = "error"
        try:
            response = await self._client.request(method, url, params=params, json=json)
            status = str(response.status_code)
            response.raise_for_status()
            return response
        finally:
            duration = time.monotonic() - start
            events_provider_requests_total.labels(
                endpoint=endpoint,
                status=status,
            ).inc()
            events_provider_request_duration_seconds.labels(
                endpoint=endpoint,
            ).observe(duration)

    @retry(
        retry=retry_if_exception_type((httpx.TimeoutException, httpx.ConnectError)),
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=1, max=10),
        reraise=True,
    )
    async def events(
        self,
        changed_at: str,
        cursor: str | None = None,
    ) -> EventsListResponse:
        """Получение списка событий с поддержкой пагинации."""
        params = {"changed_at": changed_at}
        if cursor:
            params["cursor"] = cursor

        response = await self._request(
            "GET",
            "/api/events/",
            endpoint="/events",
            params=params,
        )
        return EventsListResponse.model_validate(response.json())

    @retry(
        retry=retry_if_exception_type((httpx.TimeoutException, httpx.ConnectError)),
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=1, max=10),
        reraise=True,
    )
    async def seats(self, event_id: str) -> SeatsResponse:
        """Получение списка свободных мест для события."""
        response = await self._request(
            "GET",
            f"/api/events/{event_id}/seats/",
            endpoint="/seats",
        )
        return SeatsResponse.model_validate(response.json())

    @retry(
        retry=retry_if_exception_type((httpx.TimeoutException, httpx.ConnectError)),
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=1, max=10),
        reraise=True,
    )
    async def register(
        self,
        event_id: str,
        request: RegisterRequest,
    ) -> RegisterResponse:
        """Регистрация участника на мероприятие."""
        response = await self._request(
            "POST",
            f"/api/events/{event_id}/register/",
            endpoint="/registration",
            json=request.model_dump(),
        )
        return RegisterResponse.model_validate(response.json())

    @retry(
        retry=retry_if_exception_type((httpx.TimeoutException, httpx.ConnectError)),
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=1, max=10),
        reraise=True,
    )
    async def unregister(
        self,
        event_id: str,
        request: UnregisterRequest,
    ) -> UnregisterResponse:
        """Отмена регистрации участника."""
        response = await self._request(
            "DELETE",
            f"/api/events/{event_id}/unregister/",
            endpoint="/registration",
            json=request.model_dump(),
        )
        return UnregisterResponse.model_validate(response.json())

    async def close(self) -> None:
        """Закрытие HTTP клиента."""
        await self._client.aclose()
