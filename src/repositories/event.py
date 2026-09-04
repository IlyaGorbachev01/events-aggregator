from datetime import datetime

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from src.models.event import Event
from src.schemas.events_provider import EventResponse


class EventRepository:
    """Репозиторий для работы с событиями."""

    def __init__(self, session: AsyncSession) -> None:
        """Инициализация репозитория для работы с событиями."""
        self._session = session

    async def get(self, event_id: str) -> Event | None:
        """Получение события по ID с загруженной площадкой."""
        stmt = (
            select(Event).options(selectinload(Event.place)).where(Event.id == event_id)
        )
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()

    async def list(
        self,
        date_from: datetime | None = None,
        offset: int = 0,
        limit: int = 20,
    ) -> tuple[list[Event], int]:
        """Получение списка событий с фильтрацией и пагинацией.

        Returns:
            Кортеж из списка событий и общего количества
        """
        # Базовый запрос
        base_stmt = select(Event).options(selectinload(Event.place))

        # Фильтрация по дате
        if date_from:
            base_stmt = base_stmt.where(Event.event_time >= date_from)

        # Подсчёт общего количества
        count_stmt = select(func.count()).select_from(base_stmt.subquery())
        count_result = await self._session.execute(count_stmt)
        total = count_result.scalar() or 0

        # Пагинация и сортировка
        stmt = base_stmt.order_by(Event.event_time.desc()).offset(offset).limit(limit)
        result = await self._session.execute(stmt)
        events = result.scalars().all()

        return list(events), total

    async def upsert(self, event_data: EventResponse, place_id: str) -> Event:
        """Создание или обновление события."""
        event = await self.get(event_data.id)

        if event:
            event.name = event_data.name
            event.place_id = place_id
            event.event_time = event_data.event_time
            event.registration_deadline = event_data.registration_deadline
            event.status = event_data.status
            event.number_of_visitors = event_data.number_of_visitors
            event.changed_at = event_data.changed_at
            event.status_changed_at = event_data.status_changed_at
        else:
            event = Event(
                id=event_data.id,
                name=event_data.name,
                place_id=place_id,
                event_time=event_data.event_time,
                registration_deadline=event_data.registration_deadline,
                status=event_data.status,
                number_of_visitors=event_data.number_of_visitors,
                changed_at=event_data.changed_at,
                created_at=event_data.created_at,
                status_changed_at=event_data.status_changed_at,
            )
            self._session.add(event)

        await self._session.flush()
        return event
