# Официальный легкий образ с предустановленным Python и uv
FROM ghcr.io/astral-sh/uv:python3.13-bookworm-slim

WORKDIR /app

# Копируем файлы зависимостей
COPY pyproject.toml uv.lock ./

# Синхронизируем зависимости (без dev-пакетов для продакшена)
RUN uv sync --frozen --no-dev

# Копируем исходный код
COPY src/ ./src/

EXPOSE 8000

CMD ["uv", "run", "uvicorn", "src.main:app", "--host", "0.0.0.0", "--port", "8000"]
