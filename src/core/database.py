from collections.abc import AsyncGenerator

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase

from src.core.config import settings

engine = create_async_engine(settings.database_url, echo=settings.debug)
async_session = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


class Base(DeclarativeBase):
    """Базовый класс для всех моделей."""


async def get_session() -> AsyncGenerator[AsyncSession]:
    """Фабрика сессий для FastAPI Depends."""
    async with async_session() as session:
        yield session
