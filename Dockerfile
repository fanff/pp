# Stage 1: Build
FROM python:3.12-slim AS build

RUN pip install uv

WORKDIR /app

# Install dependencies (with dev deps for testing)
ADD pyproject.toml uv.lock .
RUN uv sync

# Copy application code
COPY ppback /app/ppback
COPY alembic /app/alembic
COPY alembic.ini /app/alembic.ini

# Stage 2: Runtime
FROM python:3.12-slim AS runtime

# Install curl for HEALTHCHECK
RUN apt-get update && apt-get install -y --no-install-recommends curl && \
    rm -rf /var/lib/apt/lists/*

# Copy uv from build stage
COPY --from=build /usr/local/bin/uv /usr/local/bin/uv

# Copy virtual environment from build stage
COPY --from=build /app/.venv /app/.venv

# Copy application code from build stage
COPY --from=build /app/ppback /app/ppback
COPY --from=build /app/alembic /app/alembic
COPY --from=build /app/alembic.ini /app/alembic.ini

WORKDIR /app

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=3s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:8000/health || exit 1

CMD ["uv", "run", "uvicorn", "ppback.main:app", "--host", "0.0.0.0", "--port", "8000"]
