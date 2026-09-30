from enum import StrEnum


class EventStatus(StrEnum):
    """Статусы событий."""

    NEW = "new"
    PUBLISHED = "published"


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
