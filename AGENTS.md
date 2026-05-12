# PP Agents Guide

Short, repo-specific notes for OpenCode agents working in this project.

## Project Shape

- Backend API: FastAPI app in `ppback/main.py` (auth, `/users`, `/conv`, `/usermsg`, `/ws`).
- DB layer: SQLAlchemy models and helpers in `ppback/db/ppdb_schemas.py` and `ppback/db/dbfuncs.py`, with Alembic migrations in `alembic/versions/`.
- TUI client: Textual app in `pp_ascii/textualpp.py` (and mirrored under `src/pp_ascii/`).
- Tracing & logging: OpenTelemetry setup in `ppback/init_tracing.py`, logging config in `ppback/logging_config.py`.

For a higher-level evolution guide, see `SKILL.md`.

## Environment & Commands

- Python: requires `>=3.12` (see `pyproject.toml`). Use `uv` for env management.
- Install deps (dev included):
  - `uv sync`
- Run backend in dev (SQLite by default):
  - `uvicorn ppback.main:app --reload`
- Initialize a fresh DB (when not using tests/compose):
  - `python -m ppback.init_db`
- Run tests:
  - `pytest`
- Compose stack (Postgres + backend + TUI SSH + Godot + Jaeger):
  - `docker compose build`
  - `docker compose up -d`

## Database & Env Quirks

- `ppback/main.py` auto-initializes the DB on import if it cannot query `UserInfo`. Be careful when pointing `DB_SESSION_STR` at a real database: starting the app may create/modify schema.
- Default dev DB URL is `sqlite:///devdb.sqlite` unless `DB_SESSION_STR` is set.
- Docker compose backend uses Postgres (`DB_SESSION_STR=postgresql://myuser:mypassword@postgres:5432/mydatabase`). Ensure migrations match when changing models.
- Tracing is enabled when `TRACING_ENDPOINT` is set; compose wires Jaeger on `http://jaeger:4318/v1/traces`.

## Testing Details

- Pytest configuration (`pytest.ini`) sets `pythonpath = "."` and `testpaths = "tests"`.
- API tests (`tests/test_api_users.py`, `tests/test_api_convs.py`) rely on the `client` fixture from `tests/conftest.py`:
  - Uses `DB_SESSION_STR` from the app (typically SQLite) but creates its own engine.
  - Creates tables via `Base.metadata.create_all` and seeds three users and two conversations.
  - Issues real `/token` calls to get OAuth2 tokens, then passes `Authorization: Bearer <token>` to endpoints.
  - Drops all tables on teardown via `Base.metadata.drop_all`.
- When changing auth, DB schemas, or `/users`/`/conv` semantics, update these tests and the fixture together.

## Auth & WebSockets

- Auth uses OAuth2 password flow at `/token`, with JWT (`HS256`) signed by `MASTER_SECRET_KEY`.
- Most endpoints take `current_user_id` via `Depends(decode_token)`. Breaking the JWT payload shape will break everything.
- WebSocket `/ws` currently performs a custom auth handshake:
  - Accepts the connection first, then expects a JSON message within 5 seconds containing `{"token": "<jwt>"}`.
  - On success, user sockets are tracked via `InMemSockets` in `ppback/wsocket.py` and used by `/usermsg` broadcasts.
- If you change authentication, you must keep this token handshake and the HTTP `/token` endpoint aligned, and update any TUI or other WS clients.

## TUI & Clients

- Textual TUI connects to the HTTP and WS backends using env vars:
  - `PPN_HOST` (HTTP base URL), `PPN_WSHOST` (WS URL).
- Docker `sshsrv` service runs the TUI over SSH:
  - Exposes port `2222`; TUI uses backend service hostnames via `PPN_HOST=http://backend:8000/`, `PPN_WSHOST=ws://backend:8000/`.
- If you change routes, auth flows, or WS protocol, adjust `pp_ascii/textualpp.py` and docker env accordingly.

## Coding Conventions

- Prefer using existing logging via `logging.getLogger("ppback")` and `setup_logging()` rather than prints.
- Keep FastAPI dependency injection patterns intact (`Depends(get_db)`, `Depends(decode_token)`), and reuse `SessionLocal` via `get_db` rather than ad-hoc engines in app code.
- When modifying DB models, update:
  - SQLAlchemy models in `ppback/db/ppdb_schemas.py`.
  - Any helpers in `ppback/db/dbfuncs.py`.
  - Alembic migrations in `alembic/versions/`.
  - Seed/init logic in `ppback/init_db.py` if it depends on the changed shape.
