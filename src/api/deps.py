from collections.abc import AsyncGenerator
from typing import Annotated

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.database import async_session
from src.services.events_provider_client import EventsProviderClient


async def get_session() -> AsyncGenerator[AsyncSession]:
    """Получение сессии БД."""
    async with async_session() as session:
        yield session


def get_events_provider_client() -> EventsProviderClient:
    """Получение клиента Events Provider API."""
    from src.core.config import settings

    return EventsProviderClient(
        base_url=settings.events_provider_base_url,
        api_key=settings.events_provider_api_key,
    )


SessionDep = Annotated[AsyncSession, Depends(get_session)]
ClientDep = Annotated[EventsProviderClient, Depends(get_events_provider_client)]
