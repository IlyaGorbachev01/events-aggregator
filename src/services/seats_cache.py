from cachetools import TTLCache


class SeatsCache:
    """Глобальный кэш свободных мест с TTL 30 секунд."""

    def __init__(self, maxsize: int = 100, ttl: int = 30) -> None:
        """Инициализирует кэш с ограничением по размеру и времени жизни записей."""
        self._cache: TTLCache = TTLCache(maxsize=maxsize, ttl=ttl)

    def get(self, event_id: str) -> list[str] | None:
        """Получить кэшированные места или None."""
        return self._cache.get(event_id)

    def set(self, event_id: str, seats: list[str]) -> None:
        """Сохранить места в кэш."""
        self._cache[event_id] = seats

    def invalidate(self, event_id: str) -> None:
        """Удалить кэш для конкретного события (например, после регистрации)."""
        self._cache.pop(event_id, None)


# Singleton для использования во всём приложении
seats_cache = SeatsCache()
