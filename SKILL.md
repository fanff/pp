# Skill: pp-evolution

## Purpose

Specialized assistant for evolving the **PP Network** project (backend API and database layer) with small, safe, test-backed changes.

## Scope

- Backend FastAPI app in `ppback/` (auth, conversations, WebSockets, admin, friends).
- Database models, migrations, and init logic in `ppback/db/` and `alembic/`.
- Local/dev tooling: `uv` workflows, pytest tests, Docker/compose files.

## Goals

- Implement new features and refactors by making the **smallest correct change**.
- Keep behaviour backwards compatible unless explicitly told otherwise.
- Maintain or improve test coverage around changed code.
- Prefer clarity over cleverness in Python code.

## Default Commands

- `uv sync` — install dependencies.
- `uvicorn ppback.main:app --reload` — run backend in dev.
- `timeout 5 uvicorn ppback.main:app --lifespan=on 2>&1 || true` — quick boot validation.
- `python -m ppback.init_db` — initialize DB manually.
- `pytest` — run tests.
- `docker compose build && docker compose up -d` — full stack (Postgres, Jaeger).

## Conventions

- Prefer incremental evolution: adjust existing modules before adding new ones.
- Keep FastAPI routes, schemas, and DB functions in sync:
  - API shapes live in `ppback/ppschema.py`.
  - DB access helpers live in `ppback/db/dbfuncs.py`.
  - Models live in `ppback/db/ppdb_schemas.py`.
- For new behaviour:
  - Add/extend Pydantic models in `ppback/ppschema.py`.
  - Add DB support in `ppback/db/` modules and migrations in `alembic/`.
  - Wire endpoints into `ppback/routers/` and register in `ppback/main.py`.
  - Add tests under `tests/`.

## Typical Workflows

1. **Backend feature or bug fix**
   1. Identify relevant endpoint(s) in `ppback/routers/` and schemas in `ppback/ppschema.py`.
   2. Inspect DB helpers and models in `ppback/db/` and `alembic/`.
   3. Implement the smallest change.
   4. Add/update tests in `tests/`.
   5. Run `pytest`.

2. **Database/schema evolution**
   1. Update models in `ppback/db/ppdb_schemas.py`.
   2. Create/adjust Alembic migration in `alembic/versions/`.
   3. Ensure `ppback/init_db.py` is coherent.
   4. Run migrations locally and verify basic flows.

3. **Docker/compose updates**
   1. Adjust `compose.yml` and `ppback_docker/Dockerfileback`.
   2. Preserve ports, env vars, and volumes.
   3. Rebuild via `docker compose build && docker compose up -d`.

## Style & Quality

- Use logging via `ppback/logging_config.py` — no ad-hoc prints.
- Keep async patterns consistent (`Depends`, `AsyncGenerator` for DB sessions).
- Prefer explicit names and small functions.
- Cached DB functions (`@cache(300)`) have a public wrapper that converts cached `dict` back to typed objects.

## Open Evolution Ideas

- Bot joining conversations.
- Fixed user colours.
- DynamoDB / DB init improvements.
