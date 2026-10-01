from enum import StrEnum


class EventStatus(StrEnum):
    """Статусы событий.

    Полный набор статусов, который возвращает Events Provider:
    new, published, registration_closed, finished.
    """

    NEW = "new"
    PUBLISHED = "published"
    REGISTRATION_CLOSED = "registration_closed"
    FINISHED = "finished"


class OutboxStatus(StrEnum):
    """Статусы записей outbox."""

    PENDING = "pending"
    SENT = "sent"
    FAILED = "failed"


class OutboxEventType(StrEnum):
    """Типы событий outbox."""

    TICKET_PURCHASED = "ticket_purchased"


class NotificationOutcome(StrEnum):
    """Результат попытки доставки уведомления во внешний сервис."""

    # Уведомление создано (HTTP 201)
    SENT = "sent"
    # Дубликат по idempotency_key (409) — засчитать как доставленное
    IDEMPOTENT_DUPLICATE = "idempotent_duplicate"
    # Временная ошибка (сеть/таймаут/5xx) — повторить позже
    RETRYABLE = "retryable"
    # Ошибка клиента (4xx) — повтор бессмысленен
    PERMANENT = "permanent"
