from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from src.api.v1 import events, health, sync, tickets
from src.core.config import settings
from src.core.exceptions import (
    EventNotFoundError,
    EventNotPublishedError,
    InvalidEmailError,
    RegistrationDeadlineError,
    SeatNotAvailableError,
    TicketNotFoundError,
)
from src.core.lifespan import lifespan
from src.core.logging import setup_logging

setup_logging()


def create_app() -> FastAPI:
    """Создание и настройка экземпляра FastAPI приложения."""
    app = FastAPI(
        title=settings.app_name,
        debug=settings.debug,
        version="0.1.0",
        lifespan=lifespan,
    )

    # Глобальный обработчик ошибок валидации Pydantic (возвращаем 400 вместо 422)
    @app.exception_handler(RequestValidationError)
    async def validation_exception_handler(
        _request: Request, exc: RequestValidationError
    ) -> JSONResponse:
        return JSONResponse(
            status_code=400,
            content={"detail": exc.errors()},
        )

    # Глобальные обработчики бизнес-исключений
    @app.exception_handler(EventNotFoundError)
    async def event_not_found_handler(
        _request: Request, exc: EventNotFoundError
    ) -> JSONResponse:
        return JSONResponse(status_code=404, content={"detail": str(exc)})

    @app.exception_handler(TicketNotFoundError)
    async def ticket_not_found_handler(
        _request: Request, exc: TicketNotFoundError
    ) -> JSONResponse:
        return JSONResponse(status_code=404, content={"detail": str(exc)})

    @app.exception_handler(EventNotPublishedError)
    async def event_not_published_handler(
        _request: Request, exc: EventNotPublishedError
    ) -> JSONResponse:
        return JSONResponse(status_code=400, content={"detail": str(exc)})

    @app.exception_handler(RegistrationDeadlineError)
    async def registration_deadline_handler(
        _request: Request, exc: RegistrationDeadlineError
    ) -> JSONResponse:
        return JSONResponse(status_code=400, content={"detail": str(exc)})

    @app.exception_handler(SeatNotAvailableError)
    async def seat_not_available_handler(
        _request: Request, exc: SeatNotAvailableError
    ) -> JSONResponse:
        return JSONResponse(status_code=400, content={"detail": str(exc)})

    @app.exception_handler(InvalidEmailError)
    async def invalid_email_handler(
        _request: Request, exc: InvalidEmailError
    ) -> JSONResponse:
        return JSONResponse(status_code=400, content={"detail": str(exc)})

    app.include_router(health.router)
    app.include_router(events.router)
    app.include_router(tickets.router)
    app.include_router(sync.router)

    return app


app = create_app()
