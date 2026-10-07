"""Middleware сбора HTTP-метрик Prometheus.

Покрывает все входящие запросы автоматически, без ручного instrumentation
в обработчиках. Пути нормализуются к route-шаблону приложения
(`/api/tickets/{ticket_id}` -> одна серия вместо бесконечного числа),
чтобы не раздувать cardinality в Prometheus.
"""

import time
from collections.abc import Awaitable, Callable

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

from src.core.metrics import http_request_duration_seconds, http_requests_total


class MetricsMiddleware(BaseHTTPMiddleware):
    """Учёт количества и длительности HTTP-запросов."""

    async def dispatch(
        self, request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        """Обработать запрос: засчитать количество и измерить длительность.

        Args:
            request: Входящий HTTP-запрос.
            call_next: Вызов следующих middleware / обработчика маршрута.

        Returns:
            Ответ приложения (без изменений).
        """
        start_time = time.monotonic()
        try:
            response = await call_next(request)
        except Exception:
            # Необработанное исключение приложения: засчитываем 500 и
            # пробрасываем дальше (отработает Sentry/ServerErrorMiddleware).
            self._record(request, 500, time.monotonic() - start_time)
            raise

        duration = time.monotonic() - start_time
        self._record(request, response.status_code, duration)

        return response

    @staticmethod
    def _record(request: Request, status_code: int, duration: float) -> None:
        """Записать счётчик и длительность запроса в метрики Prometheus.

        Args:
            request: Входящий HTTP-запрос.
            status_code: Код ответа (или 500 для необработанного исключения).
            duration: Длительность обработки в секундах.
        """
        # Нормализуем путь к шаблону маршрута (см. docstring модуля).
        # Для 404 маршрут не найден — оставляем сырой path, но cardinality
        # таких путей ограничена сканером/ботами и приемлема.
        route = request.scope.get("route")
        endpoint = getattr(route, "path_template", None) or request.url.path

        http_requests_total.labels(
            method=request.method,
            endpoint=endpoint,
            status=str(status_code),
        ).inc()

        http_request_duration_seconds.labels(
            method=request.method,
            endpoint=endpoint,
        ).observe(duration)
