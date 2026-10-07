"""Метрики Prometheus для сервиса events-aggregator.

Модуль содержит определения всех метрик (HTTP, Events Provider, бизнес-метрики
и метрики кэша) и вспомогательные функции для их обновления. Бизнес-метрики
(Gauge) заполняются значениями из БД при каждом вызове эндпоинта /metrics —
см. update_db_gauges().
"""

import asyncio
import logging

from prometheus_client import Counter, Gauge, Histogram
from sqlalchemy import Select, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.enums import TicketStatus
from src.models.event import Event
from src.models.ticket import Ticket

logger = logging.getLogger(__name__)

# --- Метрики HTTP-запросов (заполняются MetricsMiddleware) ---

http_requests_total = Counter(
    "http_requests_total",
    "Общее количество HTTP-запросов",
    ["method", "endpoint", "status"],
)

http_request_duration_seconds = Histogram(
    "http_request_duration_seconds",
    "Время обработки запросов",
    ["method", "endpoint"],
    buckets=[0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0],
)

# --- Метрики Events Provider API (заполняются EventsProviderClient) ---

events_provider_requests_total = Counter(
    "events_provider_requests_total",
    "Количество запросов к Events Provider",
    ["endpoint", "status"],
)

events_provider_request_duration_seconds = Histogram(
    "events_provider_request_duration_seconds",
    "Время ответа Events Provider",
    ["endpoint"],
    buckets=[0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0],
)

# --- Бизнес-метрики (Gauge, обновляются из БД в /metrics) ---

tickets_created_total = Gauge(
    "tickets_created_total",
    "Общее количество созданных билетов в БД",
)

tickets_cancelled_total = Gauge(
    "tickets_cancelled_total",
    "Общее количество отменённых билетов в БД",
)

events_total = Gauge(
    "events_total",
    "Текущее количество событий в базе",
)

# --- Метрики кэша ---

cache_hits_total = Counter("cache_hits_total", "Попадания в кэш (seats)")

cache_misses_total = Counter("cache_misses_total", "Промахи кэша (seats)")


async def _count(session: AsyncSession, stmt: Select) -> int:
    """Выполнить COUNT-запрос и вернуть скаляр.

    Args:
        session: Активная сессия БД.
        stmt: SELECT-подобный запрос, возвращающий одно скалярное значение.

    Returns:
        Результат запроса (0, если NULL).
    """
    result = await session.execute(stmt)
    return result.scalar() or 0


async def update_db_gauges(session: AsyncSession) -> None:
    """Обновить бизнес-Gauge актуальными значениями из БД.

    Вызывается из эндпоинта /metrics перед отдачей текста метрик.
    COUNT-запросы выполняются параллельно, чтобы не складывать задержки.
    Ошибки БД не должны ломать выдачу остальных метрик — они логируются,
    а Gauge сохраняют последнее известное значение.
    """
    try:
        events, created, cancelled = await asyncio.gather(
            _count(session, select(func.count()).select_from(Event)),
            _count(session, select(func.count()).select_from(Ticket)),
            _count(
                session,
                select(func.count())
                .select_from(Ticket)
                .where(Ticket.status == TicketStatus.CANCELLED),
            ),
        )
    except Exception:
        logger.exception("Failed to refresh DB gauges for /metrics")
        return

    events_total.set(events)
    tickets_created_total.set(created)
    tickets_cancelled_total.set(cancelled)
