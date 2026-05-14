---
name: docsync
description: >-
  Resynchronises project documentation (docs/, AGENTS.md) to reflect code
  changes. Scans uncommitted changes or recent commits, then updates all
  doc files to match current code reality.
compatibility: opencode
metadata:
  repository: pp
  domain: documentation-sync
---

# docsync — Documentation Synchronisation

## Purpose

Keep `docs/project-documentation.md`, `AGENTS.md`, and any other project docs
accurate when the code changes. Run this skill after modifying routes, schemas,
DB models, environment variables, or testing conventions.

## Detection strategy

The skill starts by checking for pending uncommitted changes:

```bash
git status --porcelain
```

### Case A — Uncommitted changes exist

The working tree or index has modifications that are likely the code changes
needing documentation sync. Study them:

```bash
git diff HEAD
git diff --cached
```

List all newly tracked / modified files and understand what changed.

### Case B — No uncommitted changes

If the working tree is clean (no pending changes), the request is about recent
history on the current branch. Scan the last 1–3 commits:

```bash
git log --oneline -3
git diff HEAD~3..HEAD
```

Use 3 commits by default; adjust to 1 if the user specifies a narrow scope.

## Files to sync

| File | Purpose |
|------|---------|
| `README.md` | High-level feature list, commands, env vars |
| `docs/project-documentation.md` | Full reference: API, schema, data model, config, testing |
| `AGENTS.md` | Agent-focused: project shape, commands, DB/auth/test quirks |
| `SKILL.md` | Skill-focused: scope, conventions, commands |
| `CONTRIBUTING.md` | Contribution workflow, branch/commit conventions |

Only update files whose content actually changed. If a file is untouched by the
code change, leave it alone (no-op).

## What to scan in the diff

For each changed file in the diff, extract the parts that affect documentation:

| Code change | Documentation impact |
|---|---|
| New/removed route in `ppback/routers/*.py` | API summary in `docs/project-documentation.md` |
| New/renamed/removed env var in `ppback/config.py` | Env table in README, docs, AGENTS |
| New/renamed/removed Pydantic schema in `ppback/ppschema.py` | API request/response shapes in docs |
| New/renamed/removed DB model in `ppback/db/ppdb_schemas.py` | Data model table in docs |
| Changed DB function signature or caching in `ppback/db/dbfuncs.py` | Caching / helpers notes |
| New/removed fixture behaviour in `tests/conftest.py` | Testing notes in docs and AGENTS |
| Changed auth flow (`deps.py`, `routers/users.py` `/token`) | Auth/WS notes |
| Changed compose / Dockerfile / env wiring | Docker section |
| Changed dependency in `pyproject.toml` | Tech stack |

## Doc update rules

1. **Never guess** — if the diff is unclear, read the relevant source files
   directly (`ppback/*.py`, `ppback/routers/*.py`, `ppback/db/*.py`).
2. **Update all affected doc files** — a route change may need updates in
   `README.md`, `docs/project-documentation.md`, and `AGENTS.md`.
3. **Keep existing structure** — preserve the file's section ordering and
   conventions; only replace stale content.
4. **Don't add comments to code** — this skill is for documentation files only.
5. **Don't add chores** — no git add/commit/push; the user decides when to
   commit doc changes.
6. **No emojis** — keep formatting plain.

## Verification

After writing each doc file, re-read it with the Read tool to verify it is
consistent and accurate. Cross-check against the actual source code for any
claims about endpoint paths, request shapes, or environment variables.

## Anti-patterns

- Prose that describes code that no longer exists.
- Claiming features that were never implemented.
- Updating docs without reading the current file content first.
- Leaving stale references to old route paths or env var names.
