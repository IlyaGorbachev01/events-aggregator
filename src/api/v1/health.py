from fastapi import APIRouter

router = APIRouter()


@router.get("/api/health", tags=["Health"])
async def health_check() -> dict[str, str]:
    """Эндпоинт для проверки доступности сервиса."""
    return {"status": "ok"}
