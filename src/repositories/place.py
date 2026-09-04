from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.models.place import Place
from src.schemas.events_provider import PlaceResponse


class PlaceRepository:
    """Репозиторий для работы с площадками."""

    def __init__(self, session: AsyncSession) -> None:
        """Инициализация репозитория для работы с площадками."""
        self._session = session

    async def get(self, place_id: str) -> Place | None:
        """Получение площадки по ID."""
        stmt = select(Place).where(Place.id == place_id)
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()

    async def upsert(self, place_data: PlaceResponse) -> Place:
        """Создание или обновление площадки."""
        place = await self.get(place_data.id)

        if place:
            place.name = place_data.name
            place.city = place_data.city
            place.address = place_data.address
            place.seats_pattern = place_data.seats_pattern
            place.changed_at = place_data.changed_at
        else:
            place = Place(
                id=place_data.id,
                name=place_data.name,
                city=place_data.city,
                address=place_data.address,
                seats_pattern=place_data.seats_pattern,
                changed_at=place_data.changed_at,
                created_at=place_data.created_at,
            )
            self._session.add(place)

        await self._session.flush()
        return place
