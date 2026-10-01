import logging

from fastapi import APIRouter, HTTPException

from src.api.deps import SessionDep
from src.core.enums import OutboxStatus
from src.repositories.outbox import OutboxRepository

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/outbox", tags=["Outbox"])


@router.get("/status")
async def outbox_status(session: SessionDep) -> dict[str, int]:
    """Состояние очереди доставки (наблюдаемость outbox-воркера).

    Возвращает количество записей по статусам и число записей, готовых
    к отправке прямо сейчас (pending с наступившим сроком попытки;
    остальные pending находятся в backoff-паузе).
    """
    repo = OutboxRepository(session)
    counts = await repo.count_by_status()
    ready_now = await repo.count_ready()
    total_pending = counts.get(OutboxStatus.PENDING.value, 0)
    return {
        "pending": total_pending,
        "ready_now": ready_now,
        "in_backoff": max(total_pending - ready_now, 0),
        "sent": counts.get(OutboxStatus.SENT.value, 0),
        "failed": counts.get(OutboxStatus.FAILED.value, 0),
    }


@router.post("/{message_id}/requeue", status_code=204)
async def requeue_failed_message(message_id: str, session: SessionDep) -> None:
    """Вернуть failed-запись outbox в очередь для повторной доставки.

    Служебная операция для re-drive событий, исчерпавших лимит попыток
    (например, после долгого простоя Capashino). Запись переводится из
    failed в pending, счётчик попыток обнуляется.

    Raises:
        HTTPException: 404 — запись не найдена или не находится в статусе
            failed (нечего переотправлять)
    """
    repo = OutboxRepository(session)
    requeued = await repo.requeue_failed(message_id)
    if not requeued:
        raise HTTPException(
            status_code=404,
            detail=(
                f"Outbox message {message_id} not found or not in 'failed' status"
            ),
        )
    logger.info("Outbox message %s manually re-queued from failed", message_id)
