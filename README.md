
## PP Network

PP Network is a backend conversational service focused on authenticated users,
conversation threads, HTTP history reads, and realtime websocket events.

Features:

* user authentication with login/password (`/token`)
* conversation management (`/conv`)
* message posting and history (`/usermsg`, `/conv/{id}/messages`)
* websocket updates (`/ws`)

## Development

Install dependencies:

```bash
uv sync
```

Run backend locally:

```bash
uvicorn ppback.main:app --reload
```

Initialize database when needed:

```bash
python -m ppback.init_db
```

Default dev credentials include `fanf:fanf` and `ted:ted`.

## Docker compose

Use `compose.yml` for backend + Postgres + Jaeger:

```bash
docker compose build
docker compose up -d
docker compose logs -f
```

## Benchmarking with Locust

Run a full benchmark campaign (fresh compose build + three-phase Locust load):

```bash
bash benchmarks/run_locust_compose.sh
```

Default load profile:

- warmup: 2 minutes
- steady: 8 minutes
- spike: 2 minutes
- traffic mix: 70% reads (`GET /users`, `GET /conv`) and 30% writes (`POST /usermsg`)

Example overrides:

```bash
BENCH_HOST="http://localhost:8000" \
LOCUST_STEADY_USERS=120 \
LOCUST_SPIKE_USERS=200 \
bash benchmarks/run_locust_compose.sh
```

Benchmark artifacts are written to `benchmarks/results/`.
