import httpx
import pytest
import respx

from src.schemas.events_provider import RegisterRequest, UnregisterRequest
from src.services.events_provider_client import EventsProviderClient


@pytest.fixture
def client() -> EventsProviderClient:
    """Фикстура для создания клиента."""
    return EventsProviderClient("http://test.com", "test-key")


@pytest.mark.asyncio
@respx.mock
async def test_events_success(client: EventsProviderClient) -> None:
    """Тест успешного получения списка событий."""
    respx.get("http://test.com/api/events/").mock(
        return_value=httpx.Response(
            200,
            json={
                "next": None,
                "previous": None,
                "results": [
                    {
                        "id": "event-1",
                        "name": "Test Event",
                        "place": {
                            "id": "place-1",
                            "name": "Test Place",
                            "city": "Moscow",
                            "address": "Test Address",
                            "seats_pattern": "A1-100",
                            "changed_at": "2026-01-01T00:00:00+00:00",
                            "created_at": "2026-01-01T00:00:00+00:00",
                        },
                        "event_time": "2026-01-11T17:00:00+03:00",
                        "registration_deadline": "2026-01-10T17:00:00+03:00",
                        "status": "published",
                        "number_of_visitors": 5,
                        "changed_at": "2026-01-04T22:28:35.325270+03:00",
                        "created_at": "2026-01-04T22:28:35.325302+03:00",
                        "status_changed_at": "2026-01-04T22:28:35.325386+03:00",
                    }
                ],
            },
        )
    )

    result = await client.events("2026-01-01")

    assert len(result.results) == 1
    assert result.results[0].id == "event-1"
    assert result.results[0].place.city == "Moscow"


@pytest.mark.asyncio
@respx.mock
async def test_events_with_cursor(client: EventsProviderClient) -> None:
    """Тест получения событий с курсором."""
    respx.get("http://test.com/api/events/").mock(
        return_value=httpx.Response(
            200,
            json={"next": None, "previous": None, "results": []},
        )
    )

    await client.events("2026-01-01", cursor="abc123")

    assert respx.calls.call_count == 1


@pytest.mark.asyncio
@respx.mock
async def test_seats_success(client: EventsProviderClient) -> None:
    """Тест успешного получения списка мест."""
    respx.get("http://test.com/api/events/event-uuid/seats/").mock(
        return_value=httpx.Response(200, json={"seats": ["A1", "A2", "B1"]})
    )

    result = await client.seats("event-uuid")

    assert result.seats == ["A1", "A2", "B1"]


@pytest.mark.asyncio
@respx.mock
async def test_register_success(client: EventsProviderClient) -> None:
    """Тест успешной регистрации."""
    respx.post("http://test.com/api/events/event-uuid/register/").mock(
        return_value=httpx.Response(201, json={"ticket_id": "ticket-uuid"})
    )

    request = RegisterRequest(
        first_name="Иван",
        last_name="Иванов",
        seat="A15",
        email="ivan@example.com",
    )
    result = await client.register("event-uuid", request)

    assert result.ticket_id == "ticket-uuid"


@pytest.mark.asyncio
@respx.mock
async def test_unregister_success(client: EventsProviderClient) -> None:
    """Тест успешной отмены регистрации."""
    respx.delete("http://test.com/api/events/event-uuid/unregister/").mock(
        return_value=httpx.Response(200, json={"success": True})
    )

    request = UnregisterRequest(ticket_id="ticket-uuid")
    result = await client.unregister("event-uuid", request)

    assert result.success is True
