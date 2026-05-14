# PP Agents Guide

Short, repo-specific notes for OpenCode agents working in this project.

## Project Shape

- Backend API: FastAPI app in `ppback/main.py`. Routers in `ppback/routers/` — `users.py`, `messaging.py`, `admin.py`, `ws.py`.
- Auth: OAuth2 password flow (`/token`), JWT HS256 with `MASTER_SECRET_KEY`. Token decode via `ppback/deps.py:decode_token`.
- DB layer: SQLAlchemy models in `ppback/db/ppdb_schemas.py`, async helpers in `ppback/db/dbfuncs.py`, connection in `ppback/db/db_connect.py`. Migrations in `alembic/`.
- Schemas: Pydantic models in `ppback/ppschema.py`.
- WebSocket: Handshake in `ppback/routers/ws.py`, socket manager in `ppback/wsocket.py`.
- Tracing & logging: OpenTelemetry in `ppback/init_tracing.py`, logging config in `ppback/logging_config.py`.
- Security: bcrypt helpers in `ppback/secu/sec_utils.py`.

For higher-level evolution guidance, see `SKILL.md`.

## Environment & Commands

- Python `>=3.12`. Use `uv` for env management.
- Install deps: `uv sync`
- Run backend in dev: `uvicorn ppback.main:app --reload`
- Quick boot validation: `timeout 5 uvicorn ppback.main:app --lifespan=on 2>&1 || true`
- Manual DB init: `python -m ppback.init_db`
- Run tests: `pytest`
- Compose stack: `docker compose build && docker compose up -d` (requires Docker Compose v2.5+)

## Database & Env Quirks

- `ppback/main.py` auto-initializes DB on import if it cannot query `UserInfo` (controlled by `PPBACK_AUTO_INIT_DB`).
- Default dev DB: `sqlite:///devdb.sqlite`.
- Compose uses Postgres with a `migrate` service that runs `alembic upgrade head`.
- Tracing enabled when `TRACING_ENDPOINT` is set; compose wires Jaeger on `http://jaeger:4318/v1/traces`.
- CI: `.github/workflows/ci.yml` runs `pytest` against SQLite and Postgres on push/PR to `main`.

## Testing Details

- Pytest config: `pytest.ini` sets `pythonpath = "."`, `testpaths = "tests"`.
- Fixture `client` in `tests/conftest.py`:
  - Overrides `DB_SESSION_STR` to `sqlite:////tmp/pp-test.sqlite`, disables auto-init.
  - Drops/creates tables, seeds 4 users (alice, bob, charlie, diana) + 2 convs + invite/friend data.
  - Issues real `/token` calls to get OAuth2 tokens for each user.
  - Resets `fastapi-cache2` between runs.
  - Tears down via `Base.metadata.drop_all`.
- Tests: `test_api_users.py`, `test_api_convs.py`, `test_api_messages_ws.py`, `test_api_admin.py`, `test_cache_types.py`.

## Auth & WebSockets

- Auth: `POST /token` with `username`/`password`. Returns JWT with `user_id` payload.
- HTTP: `Depends(decode_token)` extracts user_id from `Authorization: Bearer`.
- Admin: `Depends(require_admin)` additionally checks `user.is_admin`.
- WebSocket `/ws`: accepts connection, expects `{"token": "<jwt>"}` within 5 seconds, then tracks the socket via `InMemSockets` (max 5 sockets/user).
- WS broadcasts `MessageWS` with `type: "message.created"` — content is not included (clients fetch history).

## Coding Conventions

- Use `logging.getLogger("ppback")` and `setup_logging()` from `ppback/logging_config.py`.
- Keep FastAPI DI patterns: `Depends(get_db)`, `Depends(decode_token)`.
- Use `SessionLocal` via `get_db` — no ad-hoc engines.
- When modifying DB models, update:
  - Models in `ppback/db/ppdb_schemas.py`.
  - DB helpers in `ppback/db/dbfuncs.py`.
  - Alembic migration in `alembic/versions/`.
  - Init/seed logic in `ppback/init_db.py`.
- Cached functions in `dbfuncs.py` use the `@cache(300, key_builder=key_builder)` decorator (5 min TTL). The cache layer serializes to `dict`, so the public wrapper re-hydrates to typed objects.
