from fastapi import FastAPI

from src.api.v1 import events, health, sync, tickets
from src.core.config import settings
from src.core.lifespan import lifespan
from src.core.logging import setup_logging

# Настраиваем логирование при импорте
setup_logging()


def create_app() -> FastAPI:
    """Создание и настройка экземпляра FastAPI приложения."""
    app = FastAPI(
        title=settings.app_name,
        debug=settings.debug,
        version="0.1.0",
        lifespan=lifespan,
    )

    app.include_router(health.router)
    app.include_router(events.router)
    app.include_router(tickets.router)
    app.include_router(sync.router)

    return app


app = create_app()
