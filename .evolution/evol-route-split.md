---
id: evol-route-split
status: draft
created: 2026-05-13
authors: [franc]
related:
  - ppback/main.py
  - ppback/wsocket.py
  - ppback/ppschema.py
  - ppback/db/dbfuncs.py
  - tests/conftest.py
  - tests/test_api_users.py
  - tests/test_api_convs.py
  - tests/test_api_messages_ws.py
  - tests/test_cache_types.py
supersedes: []
superseded-by: ""
---

# Evolution: Split main.py into domain routers

## Summary

Extract route handlers from the monolithic `ppback/main.py` into three
domain-specific router modules under a new `ppback/routers/` package, with
shared dependencies (`decode_token`, `get_db`, etc.) moved to `ppback/deps.py`
and environment configuration moved to `ppback/config.py`. No API contract,
auth flow, or websocket protocol changes.

## Motivation and context

- **Current behavior**
  - `ppback/main.py` is 412 lines covering config/env, DB engine/session
    factory, OTel setup, CORS, lifespan, auth helpers (`decode_token`,
    `get_db`), and all six route/websocket handlers.
  - Three route groups share the same infrastructure but have no physical
    separation: user auth (`/token`, `/users`), messaging (`/conv`,
    `/conv/{id}/messages`, `/usermsg`), and WebSocket (`/ws`).
  - `conftest.py` and `test_cache_types.py` import `SessionLocal` and
    `dbengine` directly from `ppback.main`.
- **Problem** — Monolithic file makes it harder to:
  - reason about per-domain dependencies
  - add new routes without touching the central file
  - test routers in isolation or swap implementations
  - onboard contributors (everything is in one place with mixed concerns)
- **Why now** — The typed-cache evolution (`evol-typed-cache-outputs.md`) is
  about to land, and the route-split is a prerequisite structural improvement
  that makes subsequent changes cleaner. No functional change, low risk.
- **Constraints from current architecture**
  - Keep `/token` output shape and JWT `user_id` payload unchanged.
  - Keep `/ws` auth handshake (`{"token": "..."}` as first message).
  - Keep all existing imports from `ppback.main` working during transition
    (update immediately since scope is small: two test files).

## Goals

- `ppback/main.py` contains only app creation, lifespan, CORS middleware,
  tracing setup, and router registration (<80 lines).
- Three router modules under `ppback/routers/` each own their route group.
- Shared dependencies (`decode_token`, `get_db`, `oauth2_scheme`,
  `inmemsockets`) live in `ppback/deps.py`.
- Environment config (env vars, engine, session factory) lives in
  `ppback/config.py`.
- `inmemsockets` singleton lives in `ppback/wsocket.py` alongside the class
  definition.
- All existing tests pass without functional changes.

## Non-goals

- Changing any API route signature, response schema, or HTTP method.
- Changing JWT payload shape, OAuth flow, or websocket handshake protocol.
- Changing DB models, Alembic migrations, or `init_db` behavior.
- Adding or removing any route handler logic.
- Introducing new dependencies or frameworks.

## User-visible functionality

None. This is a pure structural refactor — all public endpoints and websocket
protocols remain identical.

## Technical approach

- **Baseline** — Single `main.py` file with all concerns mixed.
- **Proposed module layout**

  ```
  ppback/
    __init__.py
    config.py              # env vars, _to_async_db_url(), dbengine, SessionLocal
    deps.py                # oauth2_scheme, get_db, decode_token, tracer
    main.py                # app, lifespan, CORS, tracing init, include_routers
    routers/
      __init__.py
      users.py             # POST /token, GET /users
      messaging.py         # POST /conv, GET /conv, GET /conv/{id}/messages, POST /usermsg
      ws.py                # GET /ws
    wsocket.py             # class InMemSockets + singleton inmemsockets
    ... (ppschema.py, db/, secu/, etc. unchanged)
  ```

- **`config.py` responsibilities**
  - All `os.getenv(...)` calls and defaults.
  - `_to_async_db_url()` helper and `ASYNC_DB_SESSION_STR`.
  - `dbengine = create_async_engine(...)` (with pool settings).
  - `SessionLocal = async_sessionmaker(...)`.
  - Exports: `MASTER_SECRET_KEY`, `CORS_ORIGIN_STR`, `AUTO_INIT_DB`,
    `TRACING_ENDPOINT`, `HOSTNAME`, `DB_SESSION_STR`, `ASYNC_DB_SESSION_STR`,
    `dbengine`, `SessionLocal`.

- **`deps.py` responsibilities**
  - `oauth2_scheme = OAuth2PasswordBearer(tokenUrl="token")`.
  - `get_db()` — yields `AsyncSession` from `SessionLocal`, wraps in span.
  - `decode_token()` — decodes JWT, returns `user_id: int`.
  - `tracer` — module-level `trace.get_tracer(__name__)` for span creation.
  - Imports `MASTER_SECRET_KEY` and `SessionLocal` from `ppback.config`.

- **Router structure** — Each router file:
  - Creates an `APIRouter()` instance (no prefix — routes are registered at
    the same paths as today).
  - Defines its handlers using shared deps from `ppback.deps`.
  - `routers/users.py` handles `/token` and `/users`.
  - `routers/messaging.py` handles `/conv`, `/conv/{conversation_id}/messages`,
    and `/usermsg`. Imports `inmemsockets` from `ppback.wsocket` for broadcast.
  - `routers/ws.py` handles `/ws`. Uses `SessionLocal` from config directly
    (as current code does) and `decode_token` from deps. Imports
    `inmemsockets` from `ppback.wsocket`.

- **`wsocket.py` change**
  - Add `inmemsockets = InMemSockets()` at module level.
  - Remove the `inmemsockets` instantiation from `main.py`.

- **`main.py` shrinkage**
  - Remove all route handler definitions.
  - Remove `decode_token`, `get_db`, `oauth2_scheme`, `inmemsockets` init.
  - Remove env var reads and engine/session creation (now in `config.py`).
  - Keep: lifespan, `initialize_database_if_needed`, tracing setup, app
    creation, CORS middleware, `FastAPIInstrumentor.instrument_app`, and
    router registration via `app.include_router(...)`.

- **Phases** — Single PR, no phasing needed (pure refactor, no roll-forward
  risk if tests pass).

- **Alternatives considered**
  - Keeping everything in `main.py`: rejected — defeats the purpose.
  - Using `fastapi.APIRouter(prefix=...)`: rejected — route paths stay
    unchanged so no prefix needed.
  - Putting `inmemsockets` in `deps.py`: rejected — `wsocket.py` is the
    natural home and keeps deps focused on auth/DB plumbing.

- Affected modules:
  - `ppback/main.py` — major reduction
  - `ppback/wsocket.py` — add singleton instance
  - `ppback/` — new `config.py`, `deps.py`, and `routers/` package
  - `tests/conftest.py` — update import paths
  - `tests/test_cache_types.py` — update import path for `SessionLocal`

## Auth and websocket compatibility

- `/token` output remains `{"access_token": "...", "token_type": "bearer"}`.
- JWT payload continues to include `user_id`; `decode_token` remains identical
  (moved to `deps.py`).
- `/ws` handshake remains first-message JSON token packet; no protocol changes.
- `oauth2_scheme` is moved to `deps.py` but still points at `tokenUrl="token"`.
- No auth flow behavior changes whatsoever.

## Usability and documentation

- Update `AGENTS.md`:
  - Replace `ppback/main.py` references pointing to route/auth helpers with
    `ppback/config.py`, `ppback/deps.py`, and the appropriate router file.
  - Update import guidance if needed.
- `README.md` — no changes needed (run commands unaffected).

## Testability

- All existing tests must pass without modification to test logic.
- Import path updates required in:
  - `tests/conftest.py`: change `from ppback.main import SessionLocal, dbengine`
    to `from ppback.config import SessionLocal, dbengine`.
  - `tests/test_cache_types.py`: change `from ppback.main import SessionLocal`
    to `from ppback.config import SessionLocal`.
- No new tests needed — this refactor introduces zero behavioral change.
- Websocket flow validation: existing `test_api_messages_ws.py` already
  covers the `/usermsg` → WS broadcast path end-to-end.

## Complexity and rollout

- Estimated scope: **S** (pure code move with no logic changes).
- Risk hotspots:
  - Circular imports if `deps.py` and `config.py` import each other
    (prevented by design: config → deps, not the reverse).
  - Forgetting to register a router via `app.include_router()` in `main.py`.
- Rollout: single PR. If reverted, restore `main.py` to prior commit — no DB
  or migration impact.
- Rollback: `git revert` of the PR commit.

## A priori performance analysis

- Zero impact on request latency, DB query count, or websocket fan-out.
- This is a compile-time / import-time restructuring; runtime code paths are
  identical.
- Validation: all existing tests pass (including websocket integration test).

## Risks and open questions

- `routers/__init__.py` can be empty; no special init logic needed.
- Router files must import `ppback.deps` rather than `ppback.config` directly
  (to respect the dependency direction). The WS router is the exception —
  it uses `SessionLocal` directly (same pattern as current code).
- Should `routers/ws.py` switch to `get_db` instead of `SessionLocal`?
  Out of scope for this evolution — keep existing pattern.

## Decision record

- **Status**: draft
- **Resolution**:
  - Entry mode: from scratch.
  - Target file: `.evolution/evol-route-split.md`.
  - Three routers under `ppback/routers/`: `users.py`, `messaging.py`, `ws.py`.
  - Config in `ppback/config.py`, deps in `ppback/deps.py`.
  - `inmemsockets` singleton in `ppback/wsocket.py`.
  - Update two test import paths (`conftest.py`, `test_cache_types.py`).
  - Single PR, no phasing.

## References

- `ppback/main.py` — current monolithic source
- `ppback/wsocket.py` — socket tracking class
- `ppback/ppschema.py` — request/response schemas
- `tests/conftest.py` — test fixture with import path to update
- `tests/test_api_users.py` — user endpoint tests (no change needed)
- `tests/test_api_convs.py` — conversation endpoint tests (no change needed)
- `tests/test_api_messages_ws.py` — messaging + WS tests (no change needed)
- `tests/test_cache_types.py` — cache type tests (import path update)
