---
id: evol-docker-ci
status: draft
created: 2026-05-14
authors: [opencode]
related: []
supersedes: []
superseded-by: ""
---

## Summary

Fix the Dockerfile so the container actually boots, add a proper
`docker-compose.yml` with Postgres/Jaeger/migrate services, add `.dockerignore`,
add a GitHub Actions CI workflow to run tests on push/PR, add a health check
endpoint, and update `README.md` and `AGENTS.md` so documented commands match
reality.

## Motivation and context

- **Current behavior**:
  - Dockerfile is at `ppback_docker/Dockerfileback` — non-standard name and
    location that will not be auto-detected by `docker build` or `docker compose`.
  - The CMD in the Dockerfile references `ppback.thedummyAPI:app` which does
    **not exist**. The real ASGI app is at `ppback.main:app` — the container
    will crash on boot with `ModuleNotFoundError`.
  - README documents `docker compose build && docker compose up -d` but no
    `docker-compose.yml` exists in the repo root. Running that command fails
    with "no configuration file provided".
  - AGENTS.md references compose stack behavior ("Compose uses Postgres with a
    `migrate` service that runs `alembic upgrade head`") but no compose file
    defines these services — the docs describe an aspirational state.
  - No `.github/workflows/` directory exists — CI is entirely absent.
  - An `.dockerignore` file exists but it is sparse and may be incomplete.
  - No health check endpoint exists; container orchestrators cannot probe
    readiness/liveness.
- **Problem**: The Docker and CI pipeline is broken and undermines all
  container-based workflows (local dev via compose, benchmark via
  `run_locust_compose.sh`, and future deployment).
- **Why now**: Without a working compose stack, the project cannot be
  evaluated, benchmarked, or deployed by anyone other than the original
  developer. This is the foundational prerequisite for all other
  infrastructure work.
- **Constraints**:
  - Must keep backward compatibility with existing development workflows
    (`uv sync` + `uvicorn ppback.main:app --reload`).
  - Compose stack must match the existing documented services: backend,
    Postgres, Jaeger, and migrate.
  - The Dockerfile must be production-viable (multi-stage, no dev
    dependencies) while still supporting the auto-init DB behavior from
    `ppback/main.py`.

## Goals

1. Replace `ppback_docker/Dockerfileback` with a standard `Dockerfile` at
   project root with a correct `CMD` pointing to `ppback.main:app`.
2. Use multi-stage build: build stage with `uv sync` (including dev deps for
   testing) and a slim runtime stage with only production deps.
3. Add `docker-compose.yml` at project root with four services: `backend`,
   `postgres`, `jaeger`, and `migrate`.
4. Ensure `.dockerignore` is complete and prevents leaking secrets, git
   history, and virtual environments.
5. Add `.github/workflows/ci.yml` that runs `pytest` on push/PR to the main
   branch.
6. Add a `GET /health` endpoint returning `{"status": "ok"}` for container
   health probes.
7. Update `README.md` so all documented commands work.
8. Update `AGENTS.md` so compose and CI references are accurate.

## Non-goals

- No change to the application logic, API contracts, DB schema, or auth flow.
- No deployment pipeline beyond CI (no CD, no staging/production deploy).
- No docker image registry push (deferred).
- No change to the Locust benchmark setup (it is a separate evolution topic).
- No pre-built images or image caching optimization in CI.
- No changes to `ppback_docker/` other than deletion of the old file (or
  keeping it as a reference until the new `Dockerfile` is confirmed working).

## User-visible functionality

### Additive (no breaking changes)

| Endpoint | Method | Auth | Response |
|----------|--------|------|----------|
| `/health` | GET | None | `{"status": "ok"}` |

No existing endpoints, schemas, or client contracts are modified. The health
endpoint is trivially additive.

## Technical approach

### Baseline (current state)

```
ppback_docker/Dockerfileback:
  - FROM python:3.12 (single stage, no multi-stage)
  - RUN pip install uv
  - ADD pyproject.toml uv.lock .
  - RUN uv sync --no-dev
  - COPY ppback /app/ppback
  - COPY alembic /app/alembic
  - COPY alembic.ini /app/alembic.ini
  - CMD ["uv", "run", "uvicorn", "ppback.thedummyAPI:app", ...]  ← BUG
  - EXPOSE 8000

.dockerignore:   (exists but minimal)
  node_modules, .venv, .git, .gitignore, .ipynb_checkpoints, devdb, db_jaegger

docker-compose.yml:   DOES NOT EXIST
.github/workflows/:   DOES NOT EXIST
GET /health:          DOES NOT EXIST
```

### Proposed changes

#### 1. New `Dockerfile` (replaces `ppback_docker/Dockerfileback`)

Multi-stage build:

- **Stage 1 — build**: `FROM python:3.12-slim`, install `uv`, copy
  `pyproject.toml` and `uv.lock`, run `uv sync` (includes dev deps for
  testing), copy `ppback/`, `alembic/`, `alembic.ini`.
- **Stage 2 — runtime**: `FROM python:3.12-slim`, copy `uv` from build stage,
  copy installed venv from build stage, copy application code, set
  `CMD ["uv", "run", "uvicorn", "ppback.main:app", "--host", "0.0.0.0", "--port", "8000"]`,
  `EXPOSE 8000`, add `HEALTHCHECK --interval=30s --timeout=3s CMD ...` that
  curls `/health`.

Key decisions:
- Use `python:3.12-slim` instead of `python:3.12` to reduce image size.
- Keep `uv` as the package manager (consistent with local dev).
- `uv sync` in build stage; `uv sync --no-dev` or copy `.venv` selectively to
  runtime stage.
- `HEALTHCHECK` uses `curl localhost:8000/health` (install curl in runtime
  stage or use `python -c`). Given slim image size, curl adds ~3 MB — easily
  acceptable.

#### 2. New `docker-compose.yml`

```yaml
services:
  postgres:
    image: postgres:16-alpine
    environment:
      POSTGRES_USER: ppuser
      POSTGRES_PASSWORD: pppass
      POSTGRES_DB: ppdb
    ports:
      - "5432:5432"
    volumes:
      - pgdata:/var/lib/postgresql/data
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U ppuser -d ppdb"]
      interval: 5s
      timeout: 3s
      retries: 5

  migrate:
    build:
      context: .
      dockerfile: Dockerfile
    command: ["uv", "run", "alembic", "upgrade", "head"]
    environment:
      DB_SESSION_STR: postgresql+asyncpg://ppuser:ppass@postgres:5432/ppdb
      MASTER_SECRET_KEY: compose-secret-key
      PPBACK_AUTO_INIT_DB: "0"
    depends_on:
      postgres:
        condition: service_healthy

  backend:
    build:
      context: .
      dockerfile: Dockerfile
    ports:
      - "8000:8000"
    environment:
      DB_SESSION_STR: postgresql+asyncpg://ppuser:ppass@postgres:5432/ppdb
      MASTER_SECRET_KEY: compose-secret-key
      CORS_ORIGIN_STR: "*"
      TRACING_ENDPOINT: http://jaeger:4318/v1/traces
      PPBACK_AUTO_INIT_DB: "0"   # migrate service handles schema
    depends_on:
      migrate:
        condition: service_completed_successfully
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:8000/health"]
      interval: 30s
      timeout: 3s
      retries: 3

  jaeger:
    image: jaegertracing/all-in-one:latest
    ports:
      - "16686:16686"
      - "4318:4318"
    environment:
      COLLECTOR_OTLP_ENABLED: "true"
```

Key decisions:
- `PPBACK_AUTO_INIT_DB` is set to `"0"` for both `migrate` and `backend`
  because the compose stack uses Alembic migrations explicitly.
- `migrate` service runs `alembic upgrade head` and exits — it depends on
  `postgres` being healthy.
- `backend` depends on `migrate` completing successfully, not just starting.
- Jaeger uses the `all-in-one` image for simplicity (consistent with
  `TRACING_ENDPOINT` default in `config.py`).
- Health check on `backend` uses the new `/health` endpoint via `curl`.

#### 3. Updated `.dockerignore`

Additions to the existing file:
- `__pycache__/`
- `*.pyc`
- `*.pyo`
- `.env`
- `.env.*`
- `*.sqlite`
- `*.sqlite3`
- `tests/` (not needed at runtime, but keep if building for CI)
- `benchmarks/`
- `docs/`
- `.evolution/`
- `.opencode/`
- `Dockerfile` (not needed to send to daemon but harmless)
- `docker-compose.yml`
- `.github/`
- `README.md`
- `AGENTS.md`
- `.dockerignore` itself

Keep the entries that prevent leaking virtual environments and node_modules.

#### 4. New `.github/workflows/ci.yml`

```yaml
name: CI

on:
  push:
    branches: [main]
  pull_request:
    branches: [main]

jobs:
  test:
    runs-on: ubuntu-latest
    services:
      postgres:
        image: postgres:16-alpine
        env:
          POSTGRES_USER: ppuser
          POSTGRES_PASSWORD: pppass
          POSTGRES_DB: ppdb_test
        options: >-
          --health-cmd pg_isready -U ppuser -d ppdb_test
          --health-interval 5s
          --health-timeout 3s
          --health-retries 5
        ports:
          - 5432:5432

    steps:
      - uses: actions/checkout@v4

      - name: Install uv
        uses: astral-sh/setup-uv@v3

      - name: Set up Python 3.12
        uses: actions/setup-python@v5
        with:
          python-version: "3.12"

      - name: Install dependencies
        run: uv sync

      - name: Run tests (SQLite)
        run: pytest
        env:
          PPBACK_AUTO_INIT_DB: "0"

      - name: Run tests (Postgres)
        run: pytest
        env:
          DB_SESSION_STR: postgresql+asyncpg://ppuser:ppass@localhost:5432/ppdb_test
          PPBACK_AUTO_INIT_DB: "0"
```

Key decisions:
- Run tests against **both** SQLite (default dev) and Postgres (production
  parity) via the GitHub Actions `postgres` service container.
- Use `astral-sh/setup-uv` for uv installation (official and fast).
- No Docker build step in CI — tests run directly. Docker image build can
  be added in a later evolution.
- Pins only the major Python version — tests run on `ubuntu-latest` with
  Python `3.12`.

#### 5. New `GET /health` endpoint

Add to `ppback/routers/users.py` or a new `ppback/routers/health.py`:

```python
from fastapi import APIRouter

router = APIRouter()

@router.get("/health")
async def health():
    return {"status": "ok"}
```

Or simpler: add inline in `ppback/main.py` as a plain route. Since health
checks are cross-cutting and should not require dependencies (DB, auth),
putting it directly on the app or a minimal router is preferred.

Register in `ppback/main.py`:

```python
@app.get("/health")
async def health():
    return {"status": "ok"}
```

This avoids any dependency injection, DB calls, or auth. A health check that
depends on the DB would fail during rollout and cause cascading restarts. If
a deeper check is needed later, add a separate `/ready` or `/live` endpoint.

#### 6. Remove/supersede `ppback_docker/Dockerfileback`

The old file at `ppback_docker/Dockerfileback` is left in place but
documented as superseded. It can be deleted after the new `Dockerfile` is
confirmed working. The `ppback_docker/` directory can be kept for any
future Docker-related assets.

### Phases

1. **Phase 1 — Core fix**: Write new `Dockerfile`, `docker-compose.yml`,
   `.dockerignore` updates, `/health` endpoint. Verify with `docker compose up`.
2. **Phase 2 — CI**: Write `.github/workflows/ci.yml`. Verify with a PR.
3. **Phase 3 — Documentation**: Update `README.md` and `AGENTS.md` to match
   the new setup.

### Alternatives considered

- **Single-stage Dockerfile (keep as-is but fix CMD)**: Rejected because
  multi-stage reduces final image size (~150 MB vs ~1 GB) and separates build
  tools from runtime.
- **Using `uv` pip compile instead of `uv sync`**: Rejected because the project
  already standardizes on `uv sync` for local dev — the Dockerfile should
  mirror the local workflow.
- **Docker buildx / Bake**: Over-engineered for this project's scale.
- **Separate test job in CI that also builds Docker image**: Deferred. The
  CI workflow focuses on correctness (tests passing), not image publishing.
- **Health check that pings DB**: Rejected because a DB-dependent health check
  creates circular dependencies in compose (health check needs DB, DB depends
  on backend being healthy?). A simple process-liveness check is sufficient
  for this evolution.

### Affected modules

| Module | Change |
|--------|--------|
| `Dockerfile` (new, replaces `ppback_docker/Dockerfileback`) | Multi-stage build, correct CMD, HEALTHCHECK |
| `docker-compose.yml` (new) | 4 services: backend, postgres, migrate, jaeger |
| `.dockerignore` (update) | Broader exclusion patterns |
| `.github/workflows/ci.yml` (new) | pytest on push/PR with SQLite + Postgres |
| `ppback/main.py` (add `/health`) | New `GET /health` route |
| `README.md` (update) | Fix compose commands, add CI badge placeholder |
| `AGENTS.md` (update) | Fix compose references, add CI notes |

No changes to:
- `ppback/ppschema.py`
- `ppback/db/ppdb_schemas.py`
- `ppback/db/dbfuncs.py`
- `alembic/versions/*`
- `tests/conftest.py` or any test file
- `ppback/config.py`

## Auth and websocket compatibility

No impact. The `/health` endpoint is unauthenticated and does not touch auth
or websocket code. All existing auth flows (`/token`, `decode_token`,
`/ws` handshake) are completely unchanged.

## Usability and documentation

- **README.md updates**:
  - Under "Docker Compose", add directory listing of what the compose file
    starts (backend, Postgres, Jaeger, migrate).
  - Add a note that the compose stack uses Alembic for schema management
    (auto-init is disabled in compose).
  - Add a "CI" badge linking to the Actions page after first run.
- **AGENTS.md updates**:
  - Under "Environment & Commands", update the `docker compose build && docker
    compose up -d` command to reflect the new compose file.
  - Under "Database & Env Quirks", confirm that compose uses Postgres with a
    `migrate` service running `alembic upgrade head`.
  - Add a "CI" subsection under "Environment & Commands" documenting that
    `.github/workflows/ci.yml` runs tests on push/PR.
- **Error messaging**: The broken `ppback.thedummyAPI` URL was previously a
  silent boot failure. After the fix, `docker compose up` boots cleanly.

## Testability

### Unit / integration tests

No new test files needed for the Docker/CI changes. The `/health` endpoint
should be covered by a minimal test:

| Test file | Tests |
|-----------|-------|
| `tests/test_api_users.py` or new `tests/test_health.py` | `GET /health` returns `200 {"status": "ok"}` |

### Docker compose verification (manual)

```bash
# Build and boot all services
docker compose build --no-cache
docker compose up -d

# Wait for services to become healthy
docker compose ps

# Verify backend responds
curl http://localhost:8000/health

# Verify Jaeger UI is accessible
curl -s -o /dev/null -w "%{http_code}" http://localhost:16686

# Verify migrate completed (check logs)
docker compose logs migrate

# Tear down
docker compose down -v
```

### CI verification

1. Create a PR branch with these changes.
2. Push to GitHub — the Actions workflow should trigger automatically.
3. Verify both SQLite and Postgres test jobs pass in the Actions UI.

### Manual smoke check

```bash
# Start the app (old dev workflow — should still work)
uv sync
uvicorn ppback.main:app --lifespan=on

# Hit health endpoint
curl http://localhost:8000/health
# Expected: {"status":"ok"}
```

## Complexity and rollout

- **Scope**: M (medium) — ~5 new files and ~3 modified files. No database
  changes, no schema changes, no API contract changes.
- **Risk hotspots**:
  - The `docker-compose.yml` `migrate` service must complete before
    `backend` starts. The `depends_on: condition: service_completed_successfully`
    syntax requires Docker Compose v2.5+. Document this as a requirement.
  - The `HEALTHCHECK` in the Dockerfile depends on `curl` being installed
    in the runtime stage. If `curl` is omitted, the health check silently
    fails. Must ensure `curl` is installed.
  - If the postgres service port conflicts with a local postgres, the user
    needs to adjust ports or stop their local instance.
- **Rollback**: Delete the new files, revert `README.md` and `AGENTS.md`.
  The old `ppback_docker/Dockerfileback` remains as a fallback (though it
  has the broken CMD).

## A priori performance analysis

- **`/health` endpoint**: sub-millisecond, no DB, no auth. Zero impact on
  hot paths.
- **Docker image size**: Multi-stage reduces final image to ~150–200 MB
  (vs ~1 GB for the current single-stage with full `python:3.12`).
- **CI runtime**: Expected ~3–5 minutes (uv install + uv sync + pytest SQLite
  + pytest Postgres). This is acceptable for a project of this size.
- **Compose boot time**: ~15–30 seconds (Postgres health check + migrate +
  backend). Acceptable for local development.

Hypothesis: no measurable performance regression. Validate by comparing boot
time and request latency before and after (the `/health` endpoint is new so
there is no "before" baseline for it, but all existing endpoints are
unchanged).

## Risks and open questions

1. **Docker Compose v2 requirement**: The `condition: service_completed_successfully`
   syntax requires Compose v2.5+. Should we document this, or use a
   `wait-for-it.sh` script instead? **Decision: document the requirement**.
   Most modern Docker Desktop / Docker Engine installs ship with v2.5+.
   If a user has an older version, the error message from Docker is clear.
2. **uv.lock file**: Does the repo have a `uv.lock`? The Dockerfile assumes it
   exists (for `ADD uv.lock .`). If missing, the build fails. Confirm presence
   and add a lockfile if absent. **Assumption**: yes, because `uv sync` is the
   standard install command.
3. **`PPBACK_AUTO_INIT_DB=0` vs seed data**: With auto-init disabled and
   `alembic upgrade head` creating only the schema, the compose stack starts
   with an empty database (no users, no conversations). Is this acceptable for
   development? **Yes** — the compose stack is a production-like environment;
   developers can run `python -m ppback.init_db` manually or via a one-shot
   `seed` service later.
4. **`.env` file**: Should `docker-compose.yml` reference a `.env` file for
   secrets? The current approach hardcodes dev defaults (`ppuser`/`pppass`,
   `compose-secret-key`). This is acceptable for local development. A future
   evolution could add a `.env.example` and compose variable substitution.
5. **Old `ppback_docker/Dockerfileback`**: Should it be deleted immediately or
   kept until the new `Dockerfile` is confirmed working? **Decision: keep
   during phase 1, delete in phase 3** after documentation is updated.

## Decision record

- **Status**: draft
- **Resolution**: —

## References

- `ppback_docker/Dockerfileback` — current broken Dockerfile
- `ppback/main.py` — real ASGI application entry point (`ppback.main:app`)
- `ppback/config.py` — environment variables for DB, tracing, and CORS
- `README.md:37-44` — Docker Compose section (outdated)
- `AGENTS.md:24-32` — compose and DB environment documentation
- `.dockerignore` — existing incomplete file
- `tests/conftest.py` — test fixture pattern (no changes needed)
