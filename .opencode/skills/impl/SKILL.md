---
name: impl
description: >-
  Reads a PP evolution document and generates an implementation plan or code snippets.
compatibility: opencode
metadata:
  repository: pp
  domain: implementation
---

# Implementation Agent

## Purpose

The **impl** skill is used after an evolution document has been finalized. It parses the `.evolution/*.md` file, extracts goals, technical approach, testability, and risks sections, and then outputs a concrete implementation plan:

* High‑level milestones
* Required SQLAlchemy model changes (if any)
* FastAPI route or dependency updates
* Alembic migration snippets
* Test cases to add/update

The goal is to turn the abstract design into actionable code artifacts.

## Entry Modes

1. **From evolution** – Supply the path of an existing evolution file.
2. **Draft** – Provide a minimal snippet and let the skill generate the rest.

If `.evolution/` does not exist, the agent will create it when writing the first implementation file.

## Session Flow

1. Confirm target evolution file or draft content.
2. Parse the evolution markdown using a lightweight parser (frontmatter + sections).
3. For each relevant section generate:
   * SQLAlchemy model diff
   * FastAPI dependency changes
   * Alembic migration script skeleton
   * Unit test template
4. Output a single `.impl/` directory containing generated files and an `implementation.md` summary.
5. Verify that the generated code compiles against the current repo (optional).



## Guardrails

* Do not modify any existing source code directly – produce diff snippets or suggested patches.
* Keep changes within the FastAPI + SQLAlchemy stack.
* Ensure any new Alembic migration references the correct `ppback/db/` module path.
* If the evolution document contains ambiguous language, ask clarifying questions before generating code.

## Verification Checklist

- [ ] All sections of the evolution doc are addressed in the implementation plan.
- [ ] Generated SQLAlchemy models import correctly from `ppback.db.ppdb_schemas`.
- [ ] Alembic migration uses proper `op.create_table` syntax.
- [ ] Unit test file imports correct fixtures from `tests/conftest.py`.
- [ ] No linting or style violations in generated files.

---
