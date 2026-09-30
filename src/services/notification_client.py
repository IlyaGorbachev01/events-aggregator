"""Клиент Notification-сервиса (Capashino).

Воркер outbox отправляет уведомления через `POST /api/notifications`
с заголовком `X-API-Key` и обязательным `idempotency_key`, чтобы
повторная обработка записи не создавала дубликаты уведомлений.
"""

import logging

import httpx

from src.core.enums import NotificationOutcome

logger = logging.getLogger(__name__)


class NotificationDeliveryError(Exception):
    """Временная недоступность сервиса уведомлений (retryable)."""


class NotificationPermanentError(Exception):
    """Неисправимая ошибка доставки уведомления (permanent)."""


class NotificationClient:
    """Клиент для работы с Notification-сервисом (Capashino) API."""

    def __init__(self, base_url: str, api_key: str, timeout: float = 10.0) -> None:
        """Инициализация клиента Capashino.

        Args:
            base_url: Базовый URL API (из переменных окружения)
            api_key: Токен для заголовка X-API-Key (из конфигурации)
            timeout: Таймаут HTTP-запросов в секундах
        """
        self._base_url = base_url.rstrip("/")
        self._api_key = api_key
        self._client = httpx.AsyncClient(
            base_url=self._base_url,
            headers={"X-API-Key": api_key},
            timeout=timeout,
        )

    async def send_notification(
        self,
        message: str,
        reference_id: str,
        idempotency_key: str,
    ) -> NotificationOutcome:
        """Создать уведомление через POST /api/notifications.

        Повторный запрос с тем же idempotency_key не создаёт дубликат:
        ответ 409 трактуется как «уведомление уже доставлено».

        Args:
            message: Текст уведомления (не пустой после обрезки пробелов)
            reference_id: Идентификатор, с которым связывается уведомление
            idempotency_key: Ключ идемпотентности для защиты от дублей

        Returns:
            Результат попытки доставки

        Raises:
            NotificationDeliveryError: Временная ошибка (сеть/таймаут/5xx),
                попытку следует повторить позже
            NotificationPermanentError: Ошибка 4xx (кроме 409) — повтор
                бессмысленен до исправления данных/конфигурации
        """
        payload = {
            "message": message,
            "reference_id": reference_id,
            "idempotency_key": idempotency_key,
        }
        try:
            response = await self._client.post("/api/notifications", json=payload)
        except httpx.HTTPError as exc:
            raise NotificationDeliveryError(f"network error: {exc!r}") from exc

        status = response.status_code
        if status == 201:
            return NotificationOutcome.SENT
        if status == 409:
            # Уведомление с таким idempotency_key уже создано — засчитываем
            # запись как доставленную, повторная отправка не требуется.
            logger.info(
                "Notification already exists for idempotency_key=%s (HTTP 409)",
                idempotency_key,
            )
            return NotificationOutcome.IDEMPOTENT_DUPLICATE
        body = response.text[:200]
        if status >= 500:
            raise NotificationDeliveryError(f"HTTP {status}: {body}")

        # 400/401/404/422 и прочие 4xx — ошибка запроса или конфигурации;
        # повторение бессмысленно до вмешательства человека.
        raise NotificationPermanentError(f"HTTP {status}: {body}")

    async def close(self) -> None:
        """Закрытие HTTP клиента."""
        await self._client.aclose()
