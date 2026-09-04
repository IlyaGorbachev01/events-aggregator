# Events Aggregator

Backend сервис-агрегатор для работы с системой управления событиями и мероприятиями.

## Возможности

- Фоновая синхронизация событий с Events Provider API
- Удобная REST API с пагинацией и фильтрацией
- Регистрация и отмена регистрации на мероприятия
- Валидация данных и кэширование
- Retry логика для отказоустойчивости

## Технологический стек

- Python 3.13
- FastAPI
- SQLAlchemy 2.0 (async)
- PostgreSQL
- APScheduler
- Pydantic v2
- uv, ruff

## Локальный запуск

### Через Docker Compose

```bash
# Создай .env файл на основе .env.example
cp .env.example .env
# Укажи свой API ключ в .env

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

# Запуск приложения
uv run uvicorn src.main:app --reload
```

## API Endpoints

| Метод | Путь | Описание |
|-------|------|----------|
| GET | `/api/health` | Проверка доступности |
| GET | `/api/events` | Список событий (с пагинацией) |
| GET | `/api/events/{event_id}` | Детали события |
| GET | `/api/events/{event_id}/seats` | Свободные места |
| POST | `/api/tickets` | Регистрация на мероприятие |
| DELETE | `/api/tickets/{ticket_id}` | Отмена регистрации |
| POST | `/api/sync/trigger` | Ручной запуск синхронизации |

### Примеры запросов

```bash
# Список событий
curl http://localhost:8000/api/events?page=1&page_size=20

# Детали события
curl http://localhost:8000/api/events/{event_id}

# Регистрация
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

## Структура проекта

```
src/
├── api/v1/          # HTTP endpoints
├── core/            # Конфигурация, БД, lifespan, исключения
├── models/          # SQLAlchemy модели
├── repositories/    # Паттерн Repository
├── services/        # Внешние клиенты и сервисы
├── usecases/        # Бизнес-логика
└── schemas/         # Pydantic схемы
```
