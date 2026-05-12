#!/usr/bin/env bash
set -euo pipefail

COMPOSE_FILE="${COMPOSE_FILE:-compose.yml}"
BENCH_HOST="${BENCH_HOST:-http://localhost:8000}"
RESULT_DIR="${RESULT_DIR:-benchmarks/results}"
RUN_ID="${RUN_ID:-$(date +%Y%m%d-%H%M%S)}"

mkdir -p "$RESULT_DIR"

echo "[bench] resetting compose stack"
docker compose -f "$COMPOSE_FILE" down -v

echo "[bench] building fresh images"
docker compose -f "$COMPOSE_FILE" build

echo "[bench] starting compose stack"
docker compose -f "$COMPOSE_FILE" up -d

echo "[bench] waiting for backend readiness"
until curl -fsS "$BENCH_HOST/docs" >/dev/null; do
  sleep 2
done

echo "[bench] running locust headless scenario"
uv run locust \
  -f benchmarks/locustfile.py \
  --headless \
  --host "$BENCH_HOST" \
  --only-summary \
  --csv "$RESULT_DIR/$RUN_ID" \
  > "$RESULT_DIR/$RUN_ID.json"

echo "[bench] done"
echo "[bench] json: $RESULT_DIR/$RUN_ID.json"
echo "[bench] csv prefix: $RESULT_DIR/$RUN_ID"
