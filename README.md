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

Services: backend (port 8000), Postgres (5432), Jaeger UI (16686).

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
