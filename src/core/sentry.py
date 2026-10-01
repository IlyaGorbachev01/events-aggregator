"""Инициализация Sentry SDK для GlitchTip.

GlitchTip совместим с Sentry SDK. DSN выдаётся после provisioning проекта
и передаётся через переменную окружения ``SENTRY_DSN`` (не хранится в коде).
Если DSN не задан, интеграция отключается — приложение работает как раньше.
"""

import logging

import sentry_sdk
from sentry_sdk.integrations.fastapi import FastApiIntegration

from src.core.config import settings

logger = logging.getLogger(__name__)


def init_sentry() -> bool:
    """Настраивает Sentry SDK (GlitchTip), если задан SENTRY_DSN.

    Returns:
        True, если интеграция инициализирована, иначе False.
    """
    if not settings.sentry_dsn:
        logger.warning("SENTRY_DSN is not set, GlitchTip error tracking is disabled")
        return False

    sentry_sdk.init(
        dsn=settings.sentry_dsn,
        integrations=[FastApiIntegration()],
        environment=settings.sentry_environment or "production",
        release="events-aggregator@0.1.0",
        traces_sample_rate=settings.sentry_traces_sample_rate,
        send_default_pii=False,
    )
    logger.info("Sentry SDK initialized for GlitchTip")
    return True
