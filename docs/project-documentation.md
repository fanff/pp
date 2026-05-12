# PP Network - Project Documentation

## Overview

PP Network is a lightweight conversational platform built around a FastAPI backend, SQLAlchemy data models, and a Textual-based terminal UI client. It supports authenticated users, multi-user conversations, HTTP message history, and real-time updates over WebSockets.

## Repository Structure

- `ppback/`: backend API, auth, WebSocket handling, tracing, and logging.
- `ppback/db/`: SQLAlchemy models, DB helpers, and connection helpers.
- `pp_ascii/` and `src/pp_ascii/`: Textual TUI client implementation.
- `tests/`: API tests and fixtures.
- `alembic/`: migration config and versioned migration scripts.
- `compose.yml`: local multi-service stack (backend, Postgres, SSH TUI container, Godot client, Jaeger).

## Tech Stack

- Python `>=3.12`
- FastAPI + Uvicorn
- SQLAlchemy
- Alembic
- JWT auth (`pyjwt`)
- Textual (TUI)
- OpenTelemetry
- Docker Compose (optional local stack)

## Local Development

1. Install dependencies:

```bash
uv sync
```

2. Start backend in dev mode:

```bash
uvicorn ppback.main:app --reload
```

3. Initialize a fresh database when needed:

```bash
python -m ppback.init_db
```

4. Run tests:

```bash
pytest
```

### Run TUI Client Locally

```bash
export PPN_HOST="http://localhost:8000/"
export PPN_WSHOST="ws://localhost:8000/"
python -m pp_ascii.textualpp
```

## Docker Compose

Build and start all configured services:

```bash
docker compose build
docker compose up -d
```

Main exposed ports:

- `8000`: backend API
- `5432`: Postgres
- `2222`: SSH service for TUI container
- `8080`: Godot web service
- `16686`: Jaeger UI

## Configuration

Important environment variables used by the backend (`ppback/main.py`):

- `MASTER_SECRET_KEY`: JWT signing key (default: `mydummykey`).
- `DB_SESSION_STR`: SQLAlchemy DB URL (default: `sqlite:///devdb.sqlite`).
- `CORS_ORIGIN_STR`: comma-separated allowed origins (default: `*`).
- `TRACING_ENDPOINT`: enables OTLP tracing when set.

Client-related environment variables:

- `PPN_HOST`: HTTP API base URL for TUI.
- `PPN_WSHOST`: WebSocket base URL for TUI.

## API Summary

All protected HTTP endpoints require `Authorization: Bearer <token>`.

- `POST /token`
  - OAuth2 password flow endpoint.
  - Form fields: `username`, `password` (and typical OAuth `grant_type=password`).
  - Returns JWT access token.

- `GET /users`
  - Returns known users (`id`, `name`, `nickname`).

- `POST /conv`
  - Creates a conversation.
  - JSON payload:

```json
{
  "label": "My Conversation",
  "members": [1, 2]
}
```

  - Authenticated user is auto-added if missing from `members`.

- `GET /conv`
  - Returns conversations available to the current user.

- `GET /conv/{conversation_id}/messages`
  - Returns conversation messages ordered by timestamp.
  - Optional query parameter: `limit` (default `1000`).

- `POST /usermsg`
  - Stores a new message and broadcasts it to connected conversation members.
  - JSON payload:

```json
{
  "content": "hello world",
  "conversation_id": 1
}
```

## WebSocket Protocol

- Connect to: `ws://<host>/ws`
- After connection is accepted, client must send an auth packet within 5 seconds:

```json
{
  "token": "<jwt token>"
}
```

- If auth succeeds, server can broadcast message payloads in this shape:

```json
{
  "msg_id": 123,
  "originator_id": 1,
  "convo_id": 7,
  "content": "new message",
  "ts": 1712345678.123
}
```

- In-memory socket manager currently limits users to 5 concurrent sockets.

## Data Model (High Level)

- `UserInfo`: users and credentials.
- `Conv`: conversations.
- `ConvPrivacyMembers`: membership table (`conv_id`, `user_id`, `role`).
- `ConvoMessage`: message content + sender.
- `Convchanges`: timestamped conversation events linking to messages.

## Testing Notes

- Tests live in `tests/` and use FastAPI `TestClient`.
- Fixture in `tests/conftest.py` initializes tables, seeds users and conversations, retrieves real JWTs through `/token`, and drops schema on teardown.

## Operational Notes

- Backend import path auto-checks DB readiness by querying `UserInfo`; if unavailable, it initializes baseline data.
- Logging is configured through `ppback/logging_config.py`.
- Tracing is configured in `ppback/init_tracing.py` and enabled when `TRACING_ENDPOINT` is set.
