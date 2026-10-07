"""Эндпоинт /metrics для сбора метрик Prometheus.

Авторизация не требуется. Бизнес-Gauge обновляются значениями из БД
при каждом обращении (Prometheus опрашивает эндпоинт раз в 15-30 секунд,
для SELECT COUNT(*) это допустимая нагрузка).
"""

from fastapi import APIRouter
from fastapi.responses import Response
from prometheus_client import REGISTRY, generate_latest

from src.api.deps import SessionDep
from src.core.metrics import update_db_gauges

router = APIRouter(tags=["Metrics"])


@router.get("/metrics", include_in_schema=False)
async def metrics(session: SessionDep) -> Response:
    """Отдача всех зарегистрированных метрик в формате Prometheus."""
    await update_db_gauges(session)
    return Response(
        content=generate_latest(REGISTRY),
        media_type="text/plain; version=0.0.4; charset=utf-8",
    )
