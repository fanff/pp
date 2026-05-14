# PP Network - Project Documentation

## Overview

PP Network is a conversational backend built on FastAPI with SQLAlchemy. It supports authenticated users, multi-user conversations, message history, real-time WebSocket events, invite codes, friend requests, role-based conversation access, and an admin API.

## Repository Structure

```
ppback/               # Backend API, auth, WebSocket, tracing, logging
ppback/db/            # SQLAlchemy models, DB helpers, connection helpers
ppback/routers/       # Route modules (users, messaging, admin, ws)
ppback/secu/          # Security utilities (bcrypt password hashing)
tests/                # Pytest tests + conftest fixture
alembic/              # Migration config and versioned scripts
benchmarks/           # Locust load-testing suite
compose.yml           # Multi-service stack (backend, Postgres, Jaeger)
```

## Tech Stack

- Python `>=3.12`
- FastAPI + Uvicorn
- SQLAlchemy (async) + Alembic
- JWT auth (`pyjwt` / HS256)
- bcrypt password hashing
- OpenTelemetry (OTLP / Jaeger)
- fastapi-cache2 (in-memory, 5 min TTL)
- Docker Compose (Postgres, Jaeger)

## Local Development

```bash
uv sync
```

To run the full dev server (SQLite, auto-init):

```bash
uvicorn ppback.main:app --reload
```

Default credentials: `admin:admin` and `user:user`.

### Quick-startup validation

To verify imports, app boot, and DB auto-init without keeping the server running, use:

```bash
timeout 5 uvicorn ppback.main:app --lifespan=on 2>&1 || true
```

On Linux/macOS use `timeout 5`; on platforms lacking `timeout` you can use:

```bash
python -c "import asyncio, ppback.main; asyncio.run(ppback.main.initialize_database_if_needed())"
```

This validates that all modules import correctly, the DB initializes, and the app can start — then exits.

### Manual DB init

```bash
python -m ppback.init_db
```

### Run tests

```bash
pytest
```

## Docker Compose

```bash
docker compose build
docker compose up -d
```

Exposed ports:

| Port | Service |
|------|---------|
| 8000 | Backend API |
| 5432 | Postgres |
| 16686 | Jaeger UI |

Compose runs a `migrate` service (`alembic upgrade head`) before the backend starts.

## Configuration

| Variable | Default | Description |
|---|---|---|
| `MASTER_SECRET_KEY` | `mydummykey` | JWT signing key |
| `DB_SESSION_STR` | `sqlite:///devdb.sqlite` | SQLAlchemy DB URL (SQLite or Postgres) |
| `CORS_ORIGIN_STR` | `*` | Comma-separated allowed origins |
| `TRACING_ENDPOINT` | _(unset)_ | OTLP HTTP endpoint for Jaeger traces |
| `PPBACK_AUTO_INIT_DB` | `1` | Auto-create tables + seed on startup |

## API Summary

All protected endpoints require `Authorization: Bearer <token>`.

### Authentication

- **`POST /token`** — OAuth2 password flow. Form fields: `username`, `password`, `grant_type=password`. Returns `{"access_token": "...", "token_type": "bearer"}`.

### Conversations

- **`POST /conv`** — Create a conversation. Body: `{"label": "...", "members": [1, 2]}`. Creator auto-added if missing. Returns `ConversationItem`.
- **`GET /conv`** — List conversations for the current user. Cached (5 min). Returns `ConversationList`.
- **`GET /conv/{id}/messages`** — Get messages in a conversation. Query params: `limit` (default 1000), `after` (exclusive message ID cursor). Ordered by timestamp descending then reversed.

### Messages

- **`POST /usermsg`** — Post a message. Body: `{"content": "...", "conversation_id": 1}`. Validates membership + write role. Broadcasts a `MessageWS` event to connected WebSocket members.

### Users & Friends

- **`GET /users`** — List visible users (friends + conversation peers + pending request senders + self).
- **`POST /invite-codes`** — Generate an invite code for the current user.
- **`POST /friend-requests`** — Submit an invite code to send a friend request. Body: `{"invite_code": "..."}`.
- **`GET /friend-requests`** — List friend requests involving the current user.
- **`POST /friend-requests/{id}/accept`** — Accept an incoming friend request. Returns `FriendshipOut`.
- **`POST /friend-requests/{id}/reject`** — Reject an incoming friend request.
- **`GET /friends`** — List accepted friends.

### Admin (requires `is_admin`)

- **`GET /admin/users`** — List all users with admin flag and timestamps.
- **`POST /admin/users/{id}/role`** — Set user admin status. Body: `{"is_admin": true|false}`.
- **`GET /admin/conv`** — List all conversations with member counts.
- **`POST /admin/conv/{conv_id}/members/{user_id}/role`** — Set member's conversation role. Valid roles: `owner`, `admin`, `member`, `viewer`. Body: `{"role": "viewer"}`.

## WebSocket Protocol

- **Endpoint**: `ws://<host>/ws`
- **Auth**: After accept, client must send a JSON `{"token": "<jwt>"}` within 5 seconds.
- **Broadcasts**: When a message is posted, the server sends:
  ```json
  {
    "type": "message.created",
    "conversation_id": 1,
    "message_id": 123,
    "sender_id": 1,
    "ts": 1712345678.123
  }
  ```
  Note: message `content` is **not** included in the WS event (clients fetch via `GET /conv/{id}/messages`).
- **Concurrency**: max 5 sockets per user (enforced by `InMemSockets`).

## Data Model

| Table | Description |
|---|---|
| `userinfo` | Users: `name`, `email`, `nickname`, `salted_password`, `is_admin`, `created_at` |
| `conversations` | Conversations: `label`, `parent_id`, `parent_ts`, `created_at`, `updated_at` |
| `conv_members` | Membership: `conv_id`, `user_id`, `role` (owner/admin/member/viewer) |
| `convomessage` | Messages: `conv_id`, `sender_id`, `ts`, `message_type` (text/image/audio/custom), `content`, `payload` (JSON) |
| `invite_codes` | Invite codes: `code`, `creator_id`, `status`, `created_at`, `used_at`, `used_by_id` |
| `friend_requests` | Friend requests: `from_user_id`, `to_user_id`, `invite_code_id`, `status` (pending/accepted/rejected), timestamps |
| `friendships` | Bidirectional friendships: `user_a_id`, `user_b_id`, `created_at` (unique constraint) |
| `conv_starting_points` | Conversation branching: `parent_id`, `parent_ts` |

## Caching

- `fastapi-cache2` in-memory backend initialized during app lifespan.
- Cached (5 min TTL): conversation list per user, conversation members, user lookup (`hook_user`), all users query, and membership checks.
- Cache is cleared between tests in `conftest.py`.

## Logging & Tracing

- Logging configured in `ppback/logging_config.py` via `logging.config.dictConfig`. Logger: `ppback`.
- OpenTelemetry tracing in `ppback/init_tracing.py`. Enabled when `TRACING_ENDPOINT` is set. Auto-instruments FastAPI via `FastAPIInstrumentor`.

## Testing

- Tests in `tests/` use `TestClient` with WebSocket support.
- Fixture (`conftest.py`): creates SQLite DB in `/tmp`, drops/creates all tables, seeds 4 users (alice, bob, charlie, diana) with 2 conversations, one friend link, one pending friend request. Returns `(client, (alice_token, bob_token, charlie_token, diana_token))`.
- Cache is reset between each test run.

## Operations

- On startup, app queries `UserInfo`. If no users found and `PPBACK_AUTO_INIT_DB` is enabled, it creates tables and seeds `admin:admin` + `user:user` with 3 default conversations (General, Random, About).
- Async DB URL conversion (SQLite → `sqlite+aiosqlite://`, Postgres → `postgresql+asyncpg://`) is handled in `ppback/config.py`.
- Pool settings: SQLite uses defaults; Postgres uses `pool_size=10, max_overflow=20`.
