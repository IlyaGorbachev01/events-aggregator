# Events Aggregator

Backend сервис-агрегатор для работы с системой управления событиями и мероприятиями.

## Возможности

- Фоновая синхронизация событий с Events Provider API
- REST API с пагинацией и фильтрацией
- Регистрация и отмена регистрации на мероприятия
- **Transactional Outbox** — гарантированная доставка побочных действий покупки билета
- **Уведомления через Capashino** (отправка из воркера outbox)
- **Идемпотентность** операции `POST /api/tickets` (ключ в теле запроса)
- **Мониторинг ошибок через GlitchTip** (Sentry-compatible)
- Валидация данных, кэширование, retry-логика

## Технологический стек

- Python 3.13
- FastAPI
- SQLAlchemy 2.0 (async)
- PostgreSQL
- APScheduler
- Pydantic v2
- httpx, tenacity
- sentry-sdk (GlitchTip)
- uv, ruff

## Архитектура фоновых компонентов

### Transactional Outbox + воркер

Побочные действия при покупке билета (уведомление в Capashino) выполняются
через паттерн Transactional Outbox:

1. При успешной регистрации в **той же транзакции БД**, что и запись билета,
   в таблицу `outbox` сохраняется событие `ticket_purchased` с JSON-payload
   (`ticket_id`, текст уведомления `message`, данные события). Либо сохраняются
   оба, либо откатываются оба — событие не теряется при падении процесса.
2. Отдельная корутина **OutboxWorker** (запускается в lifespan FastAPI, в том
   же процессе) периодически выбирает записи со статусом `pending`
   (частичный индекс + `FOR UPDATE SKIP LOCKED`) и отправляет уведомление
   через `POST /api/notifications` сервиса Capashino
   (заголовок `X-API-Key`, `reference_id` = ticket_id, собственный
   `idempotency_key` вида `outbox:{message_id}` — дубликаты уведомлений
   исключены даже при повторной обработке записи).
3. Запись помечается `sent` только после успешного ответа Capashino (201;
   409 тоже считается успехом — уведомление уже создано). При ошибке запись
   остаётся `pending` и повторяется на следующих итерациях с экспоненциальным
   backoff'ом; после `OUTBOX_MAX_ATTEMPTS` попыток переходит в `failed`
   (событие логируется).

Параметры воркера — в переменных окружения (см. `.env.example`).

Состояние очереди можно наблюдать и чинить вручную:

| Метод | Путь | Описание |
|-------|------|----------|
| GET | `/api/outbox/status` | Счётчики pending/sent/failed + готовые к повтору |
| POST | `/api/outbox/{message_id}/requeue` | Вернуть failed-запись в pending |

### Уведомления Capashino

Базовый URL и API-ключ задаются через `CAPASHINO_BASE_URL` и
`CAPASHINO_API_KEY` (токен берётся на странице профиля портала; секрет не
хранится в коде). Из кластера используется внутренний хостнейм
`http://student-system-capashino-web.student-system-capashino.svc:8000`.

### Идемпотентность POST /api/tickets

Клиент может передать ключ идемпотентности **полем в теле запроса** —
`idempotency_key` (строка 8–128 символов, `[\w\-:.]+`):

```bash
curl -X POST http://localhost:8000/api/tickets \
  -H "Content-Type: application/json" \
  -d '{
    "event_id": "event-uuid",
    "first_name": "Иван",
    "last_name": "Иванов",
    "email": "ivan@example.com",
    "seat": "A15",
    "idempotency_key": "req-2026-10-01-001"
  }'
```

Поведение:

- **Первый запрос с ключом**: обычная регистрация (проверка события и мест,
  вызов Events Provider, сохранение билета, запись в outbox, фиксация пары
  «ключ → результат» в БД). Ответ **201** с `ticket_id`.
- **Повтор того же запроса с тем же ключом** (те же данные): новый билет НЕ
  создаётся, Events Provider НЕ вызывается — возвращается **201** с тем же
  `ticket_id`. Параллельные дубли запросов обрабатываются так же (гонка
  разрешается через уникальный PK и возврат результата победителя).
- **Тот же ключ, но другие данные** (другой event_id/seat/email/имена):
  ответ **409 Conflict**, билет не создаётся, сохранённый результат не
  перезаписывается.
- **Ошибка провайдера/валидации** (билет не создан): результат по ключу НЕ
  сохраняется — повторный запрос с тем же ключом обработается как новый.
- **Без ключа**: каждый запрос обрабатывается как новый (поведение части 1).

Срок хранения ключей задаётся `IDEMPOTENCY_KEY_TTL_HOURS`; протухшие ключи
периодически удаляются фоновой задачей планировщика.

### Синхронизация событий

Первая синхронизация выполняется сразу при старте приложения (асинхронно,
не блокируя запуск), далее — по интервалу `SYNC_INTERVAL_MINUTES`. Ручной
запуск: `POST /api/sync/trigger`.

### Мониторинг ошибок (GlitchTip)

Сервис подключён к GlitchTip через `sentry-sdk` (интеграция FastAPI): все
необработанные исключения автоматически отправляются в GlitchTip. DSN
передаётся через переменную окружения `SENTRY_DSN` (появляется после
provisioning проекта); без DSN интеграция просто отключается. Проверка
интеграции: `GET /api/health/error` (доступна при `DEBUG=true`) генерирует
тестовое исключение.

## Локальный запуск

### Через Docker Compose

```bash
# Создай .env файл на основе .env.example
cp .env.example .env
# Укажи свои API ключи в .env

# Запуск
docker compose up --build
```

Сервис будет доступен на `http://localhost:8000`

### Без Docker

```bash
# Установка зависимостей
uv sync

# Запуск PostgreSQL (например, через Docker)
docker run -d \
  --name events-aggregator-db \
  -e POSTGRES_USER=postgres \
  -e POSTGRES_PASSWORD=postgres \
  -e POSTGRES_DB=events_aggregator \
  -p 5432:5432 \
  postgres:16-alpine

# Применение миграций
uv run alembic upgrade head

# Запуск приложения (воркер outbox стартует вместе с приложением)
uv run uvicorn src.main:app --reload
```

Воркер outbox и планировщик синхронизации запускаются как корутины внутри
процесса FastAPI (lifespan) — отдельный процесс не требуется.

## API Endpoints

| Метод | Путь | Описание |
|-------|------|----------|
| GET | `/api/health` | Проверка доступности |
| GET | `/api/events` | Список событий (с пагинацией) |
| GET | `/api/events/{event_id}` | Детали события |
| GET | `/api/events/{event_id}/seats` | Свободные места |
| POST | `/api/tickets` | Регистрация (поддержка `idempotency_key` в теле) |
| DELETE | `/api/tickets/{ticket_id}` | Отмена регистрации |
| POST | `/api/sync/trigger` | Ручной запуск синхронизации |
| GET | `/api/outbox/status` | Состояние очереди outbox |
| POST | `/api/outbox/{message_id}/requeue` | Повтор failed-сообщения |

### Примеры запросов

```bash
# Список событий
curl http://localhost:8000/api/events?page=1&page_size=20

# Детали события
curl http://localhost:8000/api/events/{event_id}

# Регистрация (без ключа идемпотентности)
curl -X POST http://localhost:8000/api/tickets \
  -H "Content-Type: application/json" \
  -d '{
    "event_id": "event-uuid",
    "first_name": "Иван",
    "last_name": "Иванов",
    "email": "ivan@example.com",
    "seat": "A15"
  }'
```

## Переменные окружения

Все настройки — через переменные окружения (примеры в `.env.example`),
секреты не хранятся в репозитории:

- `DATABASE_URL` / `POSTGRES_*` — подключение к PostgreSQL;
- `EVENTS_PROVIDER_BASE_URL`, `EVENTS_PROVIDER_API_KEY` — Events Provider;
- `SYNC_INTERVAL_MINUTES` — период синхронизации;
- `OUTBOX_POLL_INTERVAL_SECONDS`, `OUTBOX_BATCH_SIZE`, `OUTBOX_MAX_ATTEMPTS`,
  `OUTBOX_BACKOFF_*` — параметры воркера outbox;
- `CAPASHINO_BASE_URL`, `CAPASHINO_API_KEY`, `CAPASHINO_TIMEOUT_SECONDS` —
  notification-сервис;
- `IDEMPOTENCY_KEY_TTL_HOURS` — срок хранения ключей идемпотентности;
- `SENTRY_DSN`, `SENTRY_ENVIRONMENT`, `SENTRY_TRACES_SAMPLE_RATE` — GlitchTip.

## Разработка

```bash
# Установка dev-зависимостей
uv sync --extra dev

# Запуск линтера
uv run ruff check .

# Автоформатирование
uv run ruff format .

# Запуск тестов
uv run pytest tests/ -v
```

CI (GitHub Actions): `ruff check` + `ruff format --check` → `pytest` →
сборка образа → деплой. Шаг линтера выполняется **до** деплоя.

## Структура проекта

```
src/
├── api/v1/          # HTTP endpoints (events, tickets, sync, outbox, health)
├── core/            # Конфигурация, БД, lifespan, исключения, sentry
├── models/          # SQLAlchemy модели (event, ticket, outbox, idempotency)
├── repositories/    # Паттерн Repository
├── services/        # Внешние клиенты (Events Provider, Capashino), воркер outbox, sync
├── usecases/        # Бизнес-логика (создание/отмена билета, места)
tests/unit/          # Юнит-тесты (клиент Capashino, воркер, идемпотентность, ...)
alembic/versions/    # Миграции (outbox, idempotency keys)
```
