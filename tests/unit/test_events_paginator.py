from unittest.mock import AsyncMock

import pytest

from src.schemas.events_provider import EventsListResponse
from src.services.events_paginator import EventsPaginator


@pytest.mark.asyncio
async def test_paginator_single_page() -> None:
    """Тест пагинации с одной страницей."""
    mock_client = AsyncMock()
    mock_client.events.return_value = EventsListResponse(
        next=None,
        previous=None,
        results=[],
    )

    paginator = EventsPaginator(mock_client, "2026-01-01")
    events = []
    async for event in paginator:
        events.append(event)

    assert len(events) == 0
    mock_client.events.assert_called_once_with("2026-01-01", None)


@pytest.mark.asyncio
async def test_paginator_multiple_pages() -> None:
    """Тест пагинации с несколькими страницами."""
    mock_client = AsyncMock()
    mock_client.events.side_effect = [
        EventsListResponse(
            next="http://test.com/api/events/?changed_at=2026-01-01&cursor=abc",
            previous=None,
            results=[],
        ),
        EventsListResponse(
            next="http://test.com/api/events/?changed_at=2026-01-01&cursor=def",
            previous="http://test.com/api/events/?changed_at=2026-01-01",
            results=[],
        ),
        EventsListResponse(
            next=None,
            previous="http://test.com/api/events/?changed_at=2026-01-01&cursor=abc",
            results=[],
        ),
    ]

    paginator = EventsPaginator(mock_client, "2026-01-01")
    events = []
    async for event in paginator:
        events.append(event)

    assert len(events) == 0
    assert mock_client.events.call_count == 3


@pytest.mark.asyncio
async def test_paginator_empty_results() -> None:
    """Тест пагинации с пустыми результатами."""
    mock_client = AsyncMock()
    mock_client.events.return_value = EventsListResponse(
        next=None,
        previous=None,
        results=[],
    )

    paginator = EventsPaginator(mock_client, "2026-01-01")
    events = []
    async for event in paginator:
        events.append(event)

    assert len(events) == 0


@pytest.mark.asyncio
async def test_paginator_custom_changed_at() -> None:
    """Тест пагинации с кастомной датой changed_at."""
    mock_client = AsyncMock()
    mock_client.events.return_value = EventsListResponse(
        next=None,
        previous=None,
        results=[],
    )

    paginator = EventsPaginator(mock_client, "2025-06-15")
    async for _event in paginator:
        pass

    mock_client.events.assert_called_once_with("2025-06-15", None)
