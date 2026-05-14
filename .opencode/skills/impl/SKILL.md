---
name: impl
description: >-
  Reads a PP evolution document and generates code snippets.
compatibility: opencode
metadata:
  repository: pp
  domain: implementation
---

# Implementation Agent

## Purpose

The **impl** skill reads a finalized evolution document (`.evolution/*.md`), extracts goals, technical approach, testability, and risks, then generates concrete code artifacts:

* SQLAlchemy model changes (if any)
* FastAPI route or dependency updates
* Alembic migration snippets
* Test cases to add/update

The goal is to turn the abstract design into actionable code.

## Entry Modes

1. **From evolution** – Supply the path of an existing evolution file.
2. **Draft** – Provide a minimal snippet and let the skill generate the rest.

## Session Flow

1. Confirm target evolution file or draft content.
2. Parse the evolution markdown (frontmatter + sections).
3. For each relevant section generate:
   * SQLAlchemy model diff
   * FastAPI dependency changes
   * Alembic migration script skeleton
   * Unit test template
4. Apply changes to the codebase.
5. Verify generated code passes tests against the current repo (optional).

## Guardrails

* Modify the code step by step.
* If the evolution document contains ambiguous language, ask clarifying questions before generating code.
* After generating code, update Alembic migrations and ensure they align with model changes.
* If modifying DB models, also update `ppback/init_db.py` and `ppback/db/dbfuncs.py` accordingly.
* Do not overwrite existing DB migration version files — create a new revision with `alembic revision --autogenerate`.

## Verification Checklist

* Run `pytest` to confirm existing tests still pass.
* If models changed, run `alembic upgrade head` on a fresh SQLite DB to verify the migration applies cleanly.
* If routes changed, verify with `uvicorn ppback.main:app --reload` that the server starts without import errors.
* Check that generated tests follow the fixture patterns in `tests/conftest.py` (OAuth2 token acquisition, `client` fixture).

---
