import hashlib
import json
import logging
from datetime import datetime

import httpx
from sqlalchemy.exc import IntegrityError

from src.core.config import settings
from src.core.enums import EventStatus, OutboxEventType
from src.core.exceptions import (
    EventNotFoundError,
    EventNotPublishedError,
    IdempotencyConflictError,
    ProviderAuthError,
    ProviderUnavailableError,
    RegistrationDeadlineError,
    SeatNotAvailableError,
    TicketNotFoundError,
)
from src.repositories.event import EventRepository
from src.repositories.idempotency import IdempotencyRepository
from src.repositories.outbox import OutboxRepository
from src.repositories.ticket import TicketRepository
from src.schemas.events_provider import RegisterRequest, UnregisterRequest
from src.services.events_provider_client import EventsProviderClient
from src.services.seats_cache import seats_cache
from src.usecases.seats import GetSeatsUsecase

logger = logging.getLogger(__name__)


def compute_request_hash(
    event_id: str,
    first_name: str,
    last_name: str,
    email: str,
    seat: str,
) -> str:
    """Канонический SHA-256 хеш данных запроса на создание билета.

    Используется для детекта конфликта: тот же ключ идемпотентности,
    но другие данные запроса. Email нормализуется к lower-case.
    """
    canonical = json.dumps(
        {
            "event_id": event_id,
            "first_name": first_name,
            "last_name": last_name,
            "email": email.lower(),
            "seat": seat,
        },
        sort_keys=True,
        ensure_ascii=False,
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


class CreateTicketUsecase:
    """UseCase для создания билета."""

    def __init__(
        self,
        client: EventsProviderClient,
        events: EventRepository,
        tickets: TicketRepository,
        outbox: OutboxRepository | None = None,
        idempotency: IdempotencyRepository | None = None,
    ) -> None:
        """Инициализация UseCase создания билета.

        Args:
            client: Клиент Events Provider API
            events: Репозиторий событий
            tickets: Репозиторий билетов
            outbox: Репозиторий outbox (опционально, для записи событий)
            idempotency: Репозиторий ключей идемпотентности (опционально)
        """
        self._client = client
        self._events = events
        self._tickets = tickets
        self._outbox = outbox
        self._idempotency = idempotency

    async def execute(
        self,
        event_id: str,
        first_name: str,
        last_name: str,
        email: str,
        seat: str,
        idempotency_key: str | None = None,
    ) -> str:
        """Создание билета с полной валидацией и поддержкой идемпотентности.

        Если передан ``idempotency_key``:
        - повтор запроса с тем же ключом и теми же данными возвращает
          ранее созданный ticket_id без повторной регистрации у провайдера;
        - тот же ключ, но другие данные -> IdempotencyConflictError (409);
        - при ошибке регистрации у провайдера результат по ключу НЕ
          сохраняется, повторный запрос с тем же ключом обработается как новый.

        Returns:
            ticket_id от провайдера
        """
        request_hash = compute_request_hash(
            event_id=event_id,
            first_name=first_name,
            last_name=last_name,
            email=email,
            seat=seat,
        )

        # Проверка уже сохранённого результата по ключу идемпотентности
        if idempotency_key is not None and self._idempotency is not None:
            existing = await self._idempotency.get(idempotency_key)
            if existing is not None:
                if existing.request_hash != request_hash:
                    raise IdempotencyConflictError(
                        f"Idempotency key {idempotency_key!r} was already used "
                        "with different request data"
                    )
                logger.info(
                    "Returning cached result for idempotency key %s (ticket %s)",
                    idempotency_key,
                    existing.ticket_id,
                )
                return existing.ticket_id

        logger.info("Creating ticket for event %s, seat %s", event_id, seat)

        # Проверяем событие
        event = await self._events.get(event_id)
        if not event:
            raise EventNotFoundError(f"Event {event_id} not found")

        # Проверяем статус события
        if event.status != EventStatus.PUBLISHED:
            raise EventNotPublishedError(f"Event {event_id} is not published")

        # Проверяем дедлайн регистрации
        now = datetime.now().astimezone()
        if now > event.registration_deadline:
            raise RegistrationDeadlineError("Registration deadline has passed")

        # Проверяем доступность места через usecase (с кэшем)
        seats_usecase = GetSeatsUsecase(self._client, self._events)
        try:
            available_seats = await seats_usecase.execute(event_id)
        except (EventNotFoundError, EventNotPublishedError):
            raise
        except (ProviderUnavailableError, ProviderAuthError) as e:
            logger.error("Failed to check seat availability: %s", e)
            raise SeatNotAvailableError("Unable to verify seat availability") from e

        if seat not in available_seats:
            raise SeatNotAvailableError(f"Seat {seat} is not available")

        # Регистрируем в провайдере
        request = RegisterRequest(
            first_name=first_name,
            last_name=last_name,
            seat=seat,
            email=email,
        )

        try:
            response = await self._client.register(event_id, request)
        except httpx.HTTPStatusError as e:
            status_code = e.response.status_code
            if status_code == 401:
                raise ProviderAuthError("Provider authentication failed") from e
            if status_code >= 500:
                raise ProviderUnavailableError("Provider unavailable") from e
            raise

        ticket_id = response.ticket_id

        # Сохраняем в своей БД
        await self._tickets.create(
            event_id=event_id,
            ticket_id=ticket_id,
            first_name=first_name,
            last_name=last_name,
            email=email,
            seat=seat,
        )

        # Пишем событие «билет куплен» в outbox — в той же транзакции,
        # что и билет. Либо сохраняются оба, либо откатываются оба.
        if self._outbox is not None:
            payload = {
                "event_type": str(OutboxEventType.TICKET_PURCHASED),
                "ticket_id": ticket_id,
                "event_id": event_id,
                "event_name": event.name,
                "first_name": first_name,
                "last_name": last_name,
                "email": email,
                "seat": seat,
                "message": (
                    f"Вы успешно зарегистрированы на мероприятие - "
                    f"{event.name}. Место: {seat}."
                ),
            }
            await self._outbox.add(
                event_type=OutboxEventType.TICKET_PURCHASED,
                payload=payload,
            )

        # Сохраняем результат по ключу идемпотентности — в той же
        # транзакции, что и билет и outbox. Если параллельный запрос с этим
        # ключом уже зафиксировал результат (IntegrityError), откатываем свою
        # транзакцию (дубликат билета не остаётся) и возвращаем чужой
        # сохранённый ticket_id — проигравший запрос становится повтором.
        if idempotency_key is not None and self._idempotency is not None:
            try:
                await self._idempotency.save(
                    key=idempotency_key,
                    request_hash=request_hash,
                    ticket_id=ticket_id,
                    response={"ticket_id": ticket_id},
                    ttl_hours=settings.idempotency_key_ttl_hours,
                )
            except IntegrityError as exc:
                # Гонка: параллельный запрос с этим ключом уже зафиксировал
                # результат. Откатываем всю транзакцию (дубликат билета не
                # остаётся) и возвращаем сохранённый ticket_id — проигравший
                # запрос становится повтором.
                await self._tickets.session.rollback()
                winner = await self._idempotency.get(idempotency_key)
                if winner is None:
                    raise IdempotencyConflictError(
                        f"Idempotency key {idempotency_key!r} conflict"
                    ) from exc
                if winner.request_hash != request_hash:
                    raise IdempotencyConflictError(
                        f"Idempotency key {idempotency_key!r} was already used "
                        "with different request data"
                    ) from exc
                logger.info(
                    "Race detected for idempotency key %s, returning winner ticket %s",
                    idempotency_key,
                    winner.ticket_id,
                )
                return winner.ticket_id

        # Инвалидируем кэш мест после регистрации
        seats_cache.invalidate(event_id)

        logger.info("Ticket created successfully: %s", ticket_id)
        return ticket_id


class CancelTicketUsecase:
    """UseCase для отмены билета."""

    def __init__(
        self,
        client: EventsProviderClient,
        tickets: TicketRepository,
    ) -> None:
        """Инициализация UseCase отмены билета.

        Args:
            client: Клиент Events Provider API
            tickets: Репозиторий билетов
        """
        self._client = client
        self._tickets = tickets

    async def execute(self, ticket_id: str) -> bool:
        """Отмена билета.

        Returns:
            True при успешной отмене
        """
        logger.info("Cancelling ticket %s", ticket_id)

        # 1. Получаем активный билет из своей БД
        # (отменённые билеты репозиторием не возвращаются -> 404)
        ticket = await self._tickets.get_by_ticket_id(ticket_id)
        if not ticket:
            raise TicketNotFoundError(f"Ticket {ticket_id} not found")

        # 2. Отменяем регистрацию в провайдере
        request = UnregisterRequest(ticket_id=ticket_id)

        try:
            response = await self._client.unregister(ticket.event_id, request)
        except httpx.HTTPStatusError as e:
            status_code = e.response.status_code
            if status_code == 401:
                raise ProviderAuthError("Provider authentication failed") from e
            if status_code >= 500:
                raise ProviderUnavailableError("Provider unavailable") from e
            raise

        if response.success:
            # 3. Мягкая отмена в своей БД (строка сохраняется со статусом
            # CANCELLED и отметкой cancelled_at)
            await self._tickets.cancel(ticket)
            # Инвалидируем кэш мест после отмены
            seats_cache.invalidate(ticket.event_id)
            logger.info("Ticket cancelled successfully: %s", ticket_id)

        return response.success
