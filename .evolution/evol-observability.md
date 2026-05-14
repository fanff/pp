---
id: evol-observability
status: draft
created: 2026-05-14
authors: [opencode]
related: []
supersedes: []
superseded-by: ""
---

## Summary

Add health checks, Prometheus metrics, request-id logging, structured logging,
and fix three technical debt items (duplicate URL conversion, Alembic sync
engine, import-time tracing ordering) so PP Network is production-observable
and the codebase is cleaner. All changes are additive — no breaking API or
websocket contract changes.

## Motivation and context

- **Current behavior**: The service has zero operational endpoints. No `GET
  /health`, no `/metrics`, no structured request logging. Tracing via
  OpenTelemetry exists (Jaeger export in `compose.yml`, `FastAPIInstrumentor`
  in `ppback/main.py:71`) but is set up at import time (`main.py:21-22`),
  before the lifespan context is available. Logging is human-readable only
  (`ppback/logging_config.py:9` — `%(levelname)s %(asctime)s %(name)s - %(message)s`).
  Docker orchestration targets (`ppback_docker/Dockerfileback:22` currently
  references `ppback.thedummyAPI:app` — likely stale) have no liveness probe.

- **Problems**:
  1. **No health check**: Container orchestrators (Kubernetes, Docker Compose
     healthchecks) have no endpoint to probe. The `compose.yml` postgres service
     has a healthcheck; the backend does not.
  2. **No metrics**: No Prometheus `/metrics` endpoint. No way to track request
     rates, p50/p99 latencies, error rates, or saturation in production.
  3. **Duplicate URL conversion**: `ppback/config.py:24-35`
     (`_to_async_db_url`, private) and `ppback/db/db_connect.py:4-15`
     (`to_async_db_url`, public) are byte-for-byte identical logic performing
     sync→async URL rewriting.
  4. **Alembic uses sync engine**: `alembic/env.py:65` calls
     `engine_from_config(...)` which creates a sync engine, while the rest of
     the project uses async SQLAlchemy. This is a mismatch that may cause
     subtle issues with async-native drivers.
  5. **No request ID correlation**: Log lines from a single HTTP request
     across different handlers cannot be correlated. Debugging a failing
     request requires matching timestamps manually.
  6. **Import-time tracing setup**: `ppback/main.py:21` calls
     `global_tracing_setup()` at module level, before `lifespan` or any
     middleware is configured. This works but is fragile — any import order
     change or conditional import can break it silently.

- **Why now**: The service is approaching production deployment (Docker Compose
  stack exists, Jaeger is wired). Without health checks and metrics,
  orchestration and monitoring are blind. The code debts (duplicate URL
  function, Alembic sync, import ordering) are small, independent fixes that
  should be cleaned up before they cause real problems.

- **Constraints**: Must not break existing API routes (`/token`, `/users`,
  `/conv`, `/usermsg`, `/ws`), token format (JWT with `user_id`), or websocket
  handshake protocol.

## Goals

1. `GET /health` endpoint returning service status (overall OK, DB connectivity,
   uptime). No authentication required.
2. `GET /metrics` endpoint exposing Prometheus metrics: request count, duration
   (histogram), in-flight requests, error count.
3. Request ID middleware: attach `X-Request-ID` header to every response,
   inject into log records for correlation.
4. Consolidate the two identical URL conversion functions into one canonical
   definition.
5. Fix `alembic/env.py` to create an async-compatible connectable (using
   `create_async_engine` + `run_sync`).
6. Add optional structured JSON logging toggled by `LOG_FORMAT=json` env var.
7. Decouple tracing setup from module import — move it into the `lifespan`
   context or a lazy initializer.

## Non-goals

- No changes to existing API contracts or response shapes.
- No addition of custom business-level metrics (e.g. "messages sent per
  conversation") — deferred to a future evolution.
- No OpenTelemetry exporter changes beyond what is already configured (OTLP
  HTTP to Jaeger). Prometheus metrics are a separate `prometheus-client`
  endpoint, not OTEL metrics export.
- No changes to the `/ws` protocol, token format, or auth flow.
- No migration of existing Alembic revisions to async — only `env.py` itself
  is fixed.
- No changes to `ppback_docker/Dockerfileback` beyond the CMD fix (stale
  reference to `thedummyAPI`).

## User-visible functionality

### Additive only — no breaking changes

| Endpoint | Method | Auth | Response |
|----------|--------|------|----------|
| `GET /health` | GET | None | `{"status": "ok", "version": "...", "db": "connected", "uptime_seconds": N}` |
| `GET /metrics` | GET | None | Prometheus text format (`text/plain; version=0.0.4`) |

**Existing behavior impact**: None. Both new endpoints are open, unauthenticated,
and mounted at new paths. `X-Request-ID` is added to every response header but
does not change any existing body or status code. Logging format changes only
when `LOG_FORMAT=json` is explicitly set.

## Technical approach

### Baseline

- `ppback/main.py`: Tracing via `global_tracing_setup()` at module import,
  `FastAPIInstrumentor.instrument_app(app)` after app creation.
- `ppback/config.py`: Owns `_to_async_db_url()` (private), engine, session
  factory creation.
- `ppback/db/db_connect.py`: Owns `to_async_db_url()` (public), used by
  `create_session_factory()` (currently not called anywhere — dead code or
  reserved for future use).
- `alembic/env.py`: Uses `engine_from_config(...)` with sync SQLAlchemy.
- `ppback/logging_config.py`: Single text formatter.

### Proposed changes

#### 1. Health endpoint (`ppback/routers/health.py`)

```python
router = APIRouter(tags=["health"])

@router.get("/health")
async def health_check(db: AsyncSession = Depends(get_db)):
    # lightweight DB ping
    await db.execute(text("SELECT 1"))
    return {
        "status": "ok",
        "db": "connected",
        "uptime_seconds": time() - startup_time,
    }
```

- No auth dependency — health endpoints must be open for load balancers.
- `startup_time` set in `lifespan` and stored as module-level float (or app
  state).
- Registered in `main.py` before other routers so it's always available.

#### 2. Prometheus metrics (`ppback/routers/metrics.py` or middleware)

Option A (recommended): Use `prometheus-client` with a custom ASGI middleware
wrapping the app. This gives full control and no extra dependency beyond
`prometheus-client`.

```python
from prometheus_client import Counter, Histogram, generate_latest, CONTENT_TYPE_LATEST
from starlette.middleware.base import BaseHTTPMiddleware

REQUEST_COUNT = Counter("pp_http_requests_total", "Total HTTP requests", ["method", "endpoint", "status"])
REQUEST_DURATION = Histogram("pp_http_request_duration_seconds", "HTTP request duration", ["method", "endpoint"])
IN_FLIGHT = Gauge("pp_http_in_flight_requests", "In-flight requests")

@router.get("/metrics")
async def metrics():
    return Response(content=generate_latest(), media_type=CONTENT_TYPE_LATEST)
```

- Middleware updates counters/histograms on each request.
- `/metrics` endpoint returns Prometheus plaintext format.
- Option B: `prometheus-fastapi-instrumentator` (less code but heavier dep).
- Recommended: Option A for minimal dependencies and explicit control.

#### 3. Request ID middleware

```python
import uuid
from starlette.middleware.base import BaseHTTPMiddleware

class RequestIDMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request, call_next):
        req_id = request.headers.get("X-Request-ID", str(uuid.uuid4()))
        # inject into logging context
        with contextvars.ContextVar("request_id", default="").set(req_id):
            response = await call_next(request)
            response.headers["X-Request-ID"] = req_id
            return response
```

- Accepts client-provided `X-Request-ID` (e.g. from a frontend) or generates
  one.
- Uses `contextvars` (Python 3.7+) so log formatters can pull `request_id`
  without passing it through every function.

#### 4. Consolidate URL conversion

- **Remove** `config.py:_to_async_db_url()`.
- **Change** `config.py` to import `to_async_db_url` from `db_connect.py`.
- `db_connect.py` remains the canonical home for URL conversion and engine
  creation helpers.
- If `db_connect.create_session_factory()` is dead code (no callers), keep it
  but mark with a comment — it may be useful for testing or alternate configs.

```python
# in config.py
from ppback.db.db_connect import to_async_db_url

ASYNC_DB_SESSION_STR = to_async_db_url(DB_SESSION_STR)
```

#### 5. Fix Alembic `env.py` for async

Change `run_migrations_online()` to use `create_async_engine` and
`run_sync`:

```python
from sqlalchemy.ext.asyncio import create_async_engine
from ppback.db.db_connect import to_async_db_url

def run_migrations_online():
    url = config.get_main_option("sqlalchemy.url")
    async_url = to_async_db_url(url)
    connectable = create_async_engine(async_url, poolclass=pool.NullPool)

    with connectable.connect() as connection:
        def do_run_migrations(conn):
            context.configure(connection=conn, target_metadata=target_metadata)
            with context.begin_transaction():
                context.run_migrations()
        connection.run_sync(do_run_migrations)
```

#### 6. Structured JSON logging

Add `LOG_FORMAT` env var support to `logging_config.py`:

```python
import os, json, logging

class JSONFormatter(logging.Formatter):
    def format(self, record):
        return json.dumps({
            "level": record.levelname,
            "timestamp": self.formatTime(record),
            "logger": record.name,
            "message": record.getMessage(),
            "request_id": getattr(record, "request_id", ""),
        })

# In setup_logging(), read os.getenv("LOG_FORMAT", "text")
# if "json", swap the formatter
```

#### 7. Move tracing setup to lifespan

In `main.py`:

```python
@asynccontextmanager
async def lifespan(app: FastAPI):
    if TRACING_ENDPOINT:
        global_tracing_setup(TRACING_ENDPOINT)
    await initialize_database_if_needed()
    cache_backend = InMemoryBackend()
    FastAPICache.init(cache_backend, prefix="fastapi-cache")
    yield
```

This requires that `FastAPIInstrumentor.instrument_app(app)` (line 71) also
move inside lifespan — or stay after app creation but before lifespan runs.
FastAPI instrumentor can be applied after app creation; the key constraint is
that `global_tracing_setup` (TracerProvider) must be called before
`instrument_app`. Both can happen inside lifespan since lifespan runs before
any request is served.

Alternative: Keep `global_tracing_setup` at module level but add a `@lru_cache`
guard so tests can re-import safely.

### Phases

1. **Phase 1 — Health + Metrics**: `routers/health.py`, middleware, `/metrics`
   endpoint, `prometheus-client` dependency. (~100 lines)
2. **Phase 2 — Request ID + Structured Logging**: middleware, JSON formatter,
   `contextvars` integration. (~60 lines)
3. **Phase 3 — Cleanup**: Consolidate URL conversion, fix Alembic `env.py`,
   move tracing to lifespan. (~30 lines across 3 files)

### Alternatives considered

- **Prometheus FastAPI Instrumentator**: Reduces boilerplate but adds a
  dependency with its own opinionated metric naming. Declined in favor of
  explicit `prometheus-client` for full control.
- **OpenTelemetry metrics exporter to Prometheus**: The project already has
  OTEL for tracing; using OTEL metrics would unify the observability surface.
  Declined because OTEL metrics are still evolving and the Prometheus endpoint
  requires the `opentelemetry-exporter-prometheus` package anyway. Simpler to
  use `prometheus-client` directly for metrics and keep OTEL for traces.
- **Keep tracing at import time**: Simpler but fragile. Moving to lifespan is
  safer and enables better test isolation.
- **Use `structlog` instead of custom JSON formatter**: Heavy dependency for a
  simple need. Custom `JSONFormatter` subclass is ~15 lines.

### Affected modules

| Module | Change |
|--------|--------|
| `ppback/routers/health.py` **new** | `GET /health` endpoint |
| `ppback/main.py` | Register health + metrics routers, add middleware, move tracing to lifespan |
| `ppback/config.py` | Replace `_to_async_db_url` with import from `db_connect.py` |
| `ppback/db/db_connect.py` | Canonical home for `to_async_db_url` (no logic change) |
| `ppback/logging_config.py` | Add `JSONFormatter`, `LOG_FORMAT` env var support |
| `alembic/env.py` | Use `create_async_engine` + `run_sync` in `run_migrations_online` |
| `pyproject.toml` | Add `prometheus-client>=0.21.0` |

## Auth and websocket compatibility

- **No impact on `/token` flow**: Health and metrics are unauthenticated. No
  token changes.
- **No impact on JWT payload**: No changes to `decode_token`, token encoding,
  or claims.
- **No impact on `/ws` handshake**: No changes to websocket routing,
  `InMemSockets`, or `MessageWS` schema.
- **Backward compatibility**: All changes are additive. Middleware adding
  `X-Request-ID` headers is transparent to clients.

## Usability and documentation

- **`GET /health`**: Returns standard status fields. Useful for Docker
  healthcheck configuration and load balancer probes.
- **`GET /metrics`**: Returns Prometheus-format metrics. Document the
  metric names (`pp_http_*`) so operators can set up dashboards and alerts.
- **Error messaging**: Health endpoint may return `503` with
  `{"status": "error", "db": "disconnected"}` if DB ping fails — but this
  should not happen during normal operation.
- **Docs to update**:
  - `README.md`: Add health check and metrics sections. Update Docker
    healthcheck configuration for the backend service in `compose.yml`.
  - `AGENTS.md`: No changes needed (observability is infra, not dev workflow).
  - Inline docstrings on new middleware and endpoints.

## Testability

### Unit / integration tests to add

| Test file | Tests |
|-----------|-------|
| `tests/test_api_health.py` **new** | `GET /health` returns 200 with expected fields |
| `tests/test_api_health.py` | `GET /health` includes `db: "connected"` |
| `tests/test_api_health.py` | `GET /health` is open (no auth required) |
| `tests/test_api_health.py` | `GET /metrics` returns 200 with `text/plain; version=0.0.4` |
| `tests/test_api_health.py` | `GET /metrics` contains `pp_http_requests_total` |
| `tests/test_logging.py` **new** | `LOG_FORMAT=json` produces valid JSON log lines |
| `tests/test_logging.py` | JSON log lines include `request_id` field |

### Existing fixture impact

- `tests/conftest.py`: No structural changes needed. The `client` fixture uses
  `TestClient(app)` which will include new middleware and routers automatically.
  If middleware is added outside the app (as app middleware in `main.py`), it is
  included. If middleware is added to the router stack, it is also included.
  No fixture changes required.

### Manual smoke check

```bash
# boot the server
uvicorn ppback.main:app --lifespan=on

# health check
curl -s http://localhost:8000/health | python3 -m json.tool
# → {"status": "ok", "db": "connected", "uptime_seconds": 2.3}

# metrics
curl -s http://localhost:8000/metrics | head -20
# → # HELP pp_http_requests_total Total HTTP requests
# → # TYPE pp_http_requests_total counter

# request ID header
curl -sI http://localhost:8000/health | grep -i x-request-id
# → x-request-id: 550e8400-e29b-41d4-a716-446655440000

# structured logging
LOG_FORMAT=json uvicorn ppback.main:app --lifespan=on 2>&1 | head -5
# → {"level": "INFO", "timestamp": "...", "logger": "ppback", "message": "...", "request_id": "..."}
```

## Complexity and rollout

- **Scope**: M (medium) — ~200 lines new code across 4 new/modified files, 1 new
  dependency (`prometheus-client`), no DB schema changes, no migration.
- **Risk hotspots**:
  - **Metrics middleware performance**: Counter/histogram updates are O(1) and
    non-blocking. The `prometheus-client` C extension is fast. Risk is low.
  - **Tracing lifespan move**: `FastAPIInstrumentor.instrument_app(app)` after
    app creation but before any requests is the standard pattern. Moving inside
    `lifespan` requires the instrumentor call to also be inside lifespan (or
    immediately after app creation, before lifespan is entered). Test with
    `timeout 5` boot test to verify instrumentation attaches correctly.
  - **Request ID contextvars**: Thread-safe by design. But if any code uses
    `asyncio.gather` or spawns tasks, the contextvar propagates correctly as
    of Python 3.12 — verify with a test that creates sub-tasks.
- **Rollback**: Revert the code changes. Remove `prometheus-client` from
  `pyproject.toml`. No DB changes to roll back. Zero impact on client-facing
  functionality.

## A priori performance analysis

- **Health endpoint**: One lightweight DB query (`SELECT 1`) per call. Called
  infrequently (orchestrator probes every 10-30s). Negligible impact.
- **Metrics middleware**: Counter/histogram increments per request. O(1) per
  request, no I/O. Prometheus exposition (`/metrics`) is off the request path
  (polled separately). Negligible impact on hot paths.
- **Request ID middleware**: UUID generation + header injection. O(1) per
  request. Measurable but trivial (< 1 µs per request).
- **Structured logging**: JSON serialization per log line is slightly more
  expensive than text formatting. For ppback's current modest request volume,
  this is invisible. If it becomes a concern, use `LOG_FORMAT=text` (default).
- **No impact on**: DB query count, websocket fan-out (`broadcast_message_to_users`),
  cache layer, or existing route handlers.

## Risks and open questions

1. **Metrics cardinality**: `pp_http_requests_total` uses `method`, `endpoint`,
   and `status` labels. If dynamic path segments (e.g. `/usermsg/{conversation_id}`)
   are included raw, cardinality explodes. **Must normalize paths** —
   e.g. replace `{conversation_id}` with `{id}` or use FastAPI route names.
   Add a normalization mapping in the middleware.
2. **Prometheus endpoint exposure**: `/metrics` is open and unauthenticated.
   In production, this endpoint should be firewalled or proxied. Consider
   adding a note in docs about network-level access control.
3. **Tracing lifespan ordering**: If `lifespan` is used for tracing setup, the
   TracerProvider must be set before `instrument_app`. Ensure the call order
   in lifespan is `global_tracing_setup → instrument_app → init_db → cache_init`.
4. **`db_connect.create_session_factory()` usage**: It is defined but appears
   unused in production code. If it's truly dead, consider removing it rather
   than keeping duplicate engine creation paths. Confirm before consolidating.
5. **Dockerfile CMD**: Currently points to `ppback.thedummyAPI:app` — this is
   likely stale. Fix as part of this evolution or file a separate issue.

## Decision record

- **Status**: draft
- **Resolution**: —

## References

- `ppback/main.py:21-22` — import-time tracing setup
- `ppback/main.py:71` — `FastAPIInstrumentor.instrument_app(app)`
- `ppback/config.py:24-35` — `_to_async_db_url()` (duplicate)
- `ppback/db/db_connect.py:4-15` — `to_async_db_url()` (canonical, duplicate)
- `ppback/logging_config.py:9` — single text-only formatter
- `alembic/env.py:65` — sync `engine_from_config`
- `ppback_docker/Dockerfileback:22` — stale `thedummyAPI` CMD reference
- `compose.yml:24-25` — `backend` service definition (no healthcheck)
