# PP Network

PP Network is a backend conversational service built on FastAPI, featuring authenticated users, conversation threads, HTTP message history, real-time WebSocket events, and a friend/invite system.

## Features

- User authentication with login/password (`/token`)
- Conversation management (`POST/GET /conv`)
- Message posting and history (`POST /usermsg`, `GET /conv/{id}/messages`)
- Real-time WebSocket updates (`/ws`)
- Invite codes and friend requests (`/invite-codes`, `/friend-requests`, `/friends`)
- Admin API (`/admin/users`, `/admin/conv`)
- Role-based access control per conversation (owner, admin, member, viewer)
- FastAPI response caching (5 min TTL for user/conversation queries)
- OpenTelemetry tracing (Jaeger) & structured logging
- Locust benchmarking suite

## Development

```bash
uv sync
uvicorn ppback.main:app --reload
```

The database is auto-initialized on startup. Manual init:

```bash
python -m ppback.init_db
```

Default dev credentials: `admin:admin` and `user:user`.

```bash
pytest
```

## Docker Compose

```bash
docker compose build
docker compose up -d
```

Services:
- **backend** — FastAPI app (port 8000)
- **postgres** — PostgreSQL 16 (port 5432)
- **migrate** — Runs `alembic upgrade head` on startup, then exits
- **jaeger** — OpenTelemetry tracing UI (port 16686, OTLP 4318)

The compose stack uses Alembic for schema management (auto-init is disabled).

## Benchmarking

```bash
bash benchmarks/run_locust_compose.sh
```

Default profile: 2m warmup, 8m steady, 2m spike (70% reads / 30% writes).

## Environment

| Variable | Default | Description |
|---|---|---|
| `MASTER_SECRET_KEY` | `mydummykey` | JWT signing key |
| `DB_SESSION_STR` | `sqlite:///devdb.sqlite` | SQLAlchemy DB URL |
| `CORS_ORIGIN_STR` | `*` | Comma-separated allowed origins |
| `TRACING_ENDPOINT` | _(unset)_ | OTLP endpoint for Jaeger traces |
| `PPBACK_AUTO_INIT_DB` | `1` | Enable/disable auto-init |

## CI

Tests run automatically via GitHub Actions on every push/PR to the `main` branch.
The workflow runs `pytest` against both SQLite (default) and PostgreSQL (production parity).

[![CI](https://github.com/YOUR_ORG/pp-network/actions/workflows/ci.yml/badge.svg)](https://github.com/YOUR_ORG/pp-network/actions/workflows/ci.yml)

Replace `YOUR_ORG` with your GitHub organization or username in the badge URL above.
