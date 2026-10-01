from fastapi import APIRouter

from src.core.config import settings

router = APIRouter()


@router.get("/api/health", tags=["Health"])
async def health_check() -> dict[str, str]:
    """Эндпоинт для проверки доступности сервиса."""
    return {"status": "ok"}


@router.get("/api/health/error", tags=["Health"])
async def health_error_check() -> dict[str, str]:
    """Тестовый эндпоинт для проверки интеграции с GlitchTip.

    Доступен только при DEBUG=true. Генерирует необработанное исключение,
    которое должно появиться в интерфейсе GlitchTip.
    """
    if not settings.debug:
        return {"status": "disabled"}
    msg = "Test exception for GlitchTip integration verification"
    raise RuntimeError(msg)
