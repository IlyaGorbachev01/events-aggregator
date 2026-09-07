from enum import StrEnum


class EventStatus(StrEnum):
    """Статусы событий."""

    NEW = "new"
    PUBLISHED = "published"
