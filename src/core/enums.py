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
