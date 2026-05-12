# Skill: pp-evolution

## Purpose

Specialized assistant for evolving the **PP Network** project (backend API and database layer) with small, safe, test-backed changes.

The skill assumes it is always running inside this repository (`pp`) and that the code here is the single source of truth.

## Scope

- Backend FastAPI app in `ppback/` (auth, conversations, WebSockets).
- Database models, migrations, and init logic in `ppback/db/` and `alembic/`.
- Local/dev tooling: `uv` workflows, pytest tests, Docker/compose files.

## Goals

- Implement new features and refactors by making the **smallest correct change**.
- Keep behaviour backwards compatible unless explicitly told otherwise.
- Maintain or improve test coverage around changed code.
- Prefer clarity over cleverness in Python code.

## Default Commands

- Set up env (from README):
  - `uv sync`
- Run backend in dev:
  - `uvicorn ppback.main:app --reload`
- Initialize local database (if needed):
  - `python -m ppback.init_db`
- Run tests:
  - `pytest`
- Build & run full stack via Docker:
  - `docker compose build`
  - `docker compose up -d`

## Conventions

- Prefer incremental evolution: adjust existing modules before adding new ones.
- Keep FastAPI routes, schemas, and DB functions in sync:
  - API shapes live in `ppback/ppschema.py` and related models.
  - Database access helpers live in `ppback/db/dbfuncs.py` and `ppback/db/ppdb_schemas.py`.
- For new behaviour:
  - Add/extend pydantic models in `ppback/ppschema.py`.
  - Add DB support in `ppback/db` modules and migrations in `alembic/` when schema changes.
  - Wire endpoints into `ppback/main.py`.
  - Add tests under `tests/`.
## Typical Workflows

1. **Backend feature or bug fix**
   1. Identify relevant endpoint(s) in `ppback/main.py` and schemas in `ppback/ppschema.py`.
   2. Inspect DB helpers and models in `ppback/db/` and `alembic/` if data shape is involved.
   3. Implement the smallest change that satisfies the new behaviour.
   4. Add or update tests in `tests/`.
   5. Run `pytest` and summarize failures/success.

2. **Database/schema evolution**
   1. Update SQLAlchemy models in `ppback/db/ppdb_schemas.py`.
   2. Create or adjust Alembic migration under `alembic/versions/`.
   3. Ensure `ppback/init_db.py` is still coherent with the new schema.
   4. Run migrations locally and verify basic app flows.

3. **Docker / compose updates**
   1. Adjust `compose.yml` and Dockerfiles under `ppback_docker/`.
   2. Preserve existing ports, env vars, and volumes unless change is requested.
   3. Rebuild and start via `docker compose build` and `docker compose up -d`.

## Style & Quality

- Use logging via `ppback/logging_config.py` instead of ad-hoc prints in backend code.
- Keep async patterns consistent with existing FastAPI usage (e.g. `Depends`, `AsyncGenerator` for DB sessions).
- Add brief comments where logic is non-obvious, not for trivial steps.
- Prefer explicit names and small functions over deep call stacks.

## Open Evolution Ideas

Ideas already hinted by the project README TODOs that this skill may help with:

- Backend:
  - Bot joining conversations.
  - Fixed user colours.
  - DynamoDB / DB init improvements.
