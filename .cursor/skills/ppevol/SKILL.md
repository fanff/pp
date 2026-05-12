---
name: ppevol
description: >-
  Facilitates structured Q&A to author PP Network evolution documents under
  `.evolution/` (versioned markdown). Grounds proposals in this repo's FastAPI,
  DB, and Textual client architecture so changes stay testable and coherent.
  Use when discussing design proposals, roadmaps, architecture changes, or
  creating/updating evolution docs.
disable-model-invocation: true
---

# PP evolution documents

## Purpose

Guide collaborative writing of **evolution documents** for PP Network: markdown
files under `.evolution/` that capture what should change, why, and how to
verify it before implementation.

## Start here: project grounding

Before asking the first question, read enough repo context to avoid generic
advice and keep proposals aligned with PP:

| File | Why |
|------|-----|
| [`README.md`](../../../README.md) | Product intent, local run commands, docker usage |
| [`AGENTS.md`](../../../AGENTS.md) | Repo shape, auth/WS constraints, DB/test quirks |
| [`ppback/main.py`](../../../ppback/main.py) | Current API routes, auth deps, websocket flow |
| [`ppback/db/ppdb_schemas.py`](../../../ppback/db/ppdb_schemas.py) and [`ppback/db/dbfuncs.py`](../../../ppback/db/dbfuncs.py) | Data model and persistence behavior |
| [`tests/conftest.py`](../../../tests/conftest.py) and API tests in [`tests/`](../../../tests/) | Current behavior contract and fixture assumptions |
| [`pp_ascii/textualpp.py`](../../../pp_ascii/textualpp.py) | TUI backend contract expectations |

Skim other touched files as needed; stay anchored to existing conventions.

## Entry modes

Pick one mode at the start (confirm if unclear):

1. **From scratch** - New evolution doc from template.
2. **Recover** - Existing draft has gaps; fill and de-risk it.
3. **Reference** - Mirror style/depth from user-named evolution docs.

If `.evolution/` is missing, create it when writing the first file.

## Document standard

- One file per evolution under `.evolution/`, kebab-case name.
- Prefer `evol-<topic>.md` unless sibling files use a different pattern.
- Follow section order from [template.md](template.md).
- Frontmatter is optional but recommended (`id`, `status`, `related`).

## Session scope

Work on **one target evolution file** per session unless the user explicitly
asks for cross-evolution reconciliation.

- Keep internal consistency across all sections in that one target file.
- In reference mode, read only user-requested reference evolutions.

## Conversation protocol

- Ask **one or two focused questions** per turn.
- For each question, include a concise suggested answer based on repo context.
- Accept response shorthand:
  - `n:y` to accept suggestion `n`
  - `n:n` or `n:no` to reject and provide alternative
  - `n: <free text>` for custom input
  - `1:y, 2: ...` for batching

Treat user edits to the evolution file as authoritative and propagate the change
through Summary, Goals, Non-goals, Technical approach, Testability, Risks, and
Decision record.

## Challenge dimensions

Cover these lenses across the session:

| Lens | Challenge |
|------|-----------|
| **Functionality** | Exact route/schema/behavior changes and affected users/clients |
| **Compatibility** | Backwards compatibility for `/token`, JWT payload, `/ws` handshake, and TUI expectations |
| **Technical design** | FastAPI deps, DB helpers, migrations, and websocket socket-tracking impacts |
| **Testability** | Unit/API coverage, fixture updates, websocket and auth regression checks |
| **Complexity** | Scope sizing, phased rollout, and rollback options |
| **A priori performance** | Expected impact on query count, per-message fan-out, and request latency hotspots |

Be explicit about hypotheses versus measured results.

## Session flow

1. Confirm mode and target `.evolution/*.md` filename.
2. Read relevant repo files for touched areas.
3. Summarize understanding in <=5 lines; ask first 1-2 questions.
4. Iterate until template sections are concrete and implementable.
5. Write/update the target markdown file under `.evolution/`.
6. Re-read the file once to remove internal contradictions.

Only commit or create branches when the user explicitly requests git actions.

## PP-specific guardrails

- Keep auth flow coherent: `/token` output and `decode_token` expectations must
  remain compatible.
- Keep websocket auth handshake aligned with clients: first message must include
  token JSON.
- If DB schema changes, include SQLAlchemy model updates, migration updates,
  and `init_db` implications.
- If API contracts change, include TUI updates (`PPN_HOST`/`PPN_WSHOST` usage)
  and docker/env notes when relevant.
- Prefer incremental, test-backed slices over broad rewrites.

## Anti-patterns

- Proposing architecture detached from current FastAPI + SQLAlchemy + Textual stack.
- Defining goals without validation steps in tests.
- Ignoring auth/ws coupling while modifying user/conversation/message flows.
- Changing DB shape without mentioning Alembic or fixture impact.
- Finalizing docs while sections still contradict each other.

## Verification checklist

- [ ] README and AGENTS context read for touched areas.
- [ ] Entry mode and target file confirmed.
- [ ] All template sections filled or marked N/A with rationale.
- [ ] Auth, websocket, DB migration, and TUI contract impacts considered.
- [ ] Test plan includes affected API and/or websocket behavior.
- [ ] File saved under `.evolution/` with repo-consistent naming.
