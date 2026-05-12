# Evolution: <short title>

Use this template for PP Network evolution docs under `.evolution/`.
Replace placeholders and delete sections that are truly not applicable.

```yaml
# Optional frontmatter (recommended)
id: evol-<short-slug>
status: draft   # draft | proposed | accepted | superseded
created: YYYY-MM-DD
authors: [<name-or-handle>]
related: []     # issues, PRs, prior evolutions, docs
supersedes: []
superseded-by: ""
```

## Summary

One paragraph: what changes, who is affected, and why now.

## Motivation and context

- **Current behavior** - Describe current API, DB, and client behavior, with
  links to code paths.
- Problem or limitation in current behavior.
- Why now (bug risk, feature need, operational pain, or UX friction).
- Constraints from current architecture (FastAPI auth, websocket flow, DB setup,
  TUI coupling).

## Goals

Concrete and verifiable outcomes.

## Non-goals

Explicit boundaries and deferred work.

## User-visible functionality

- API and behavior changes users will notice.
- Breaking vs additive changes; migration notes if needed.
- TUI-visible changes if any.

## Technical approach

- **Baseline** - How the relevant flow works now.
- **Proposed change** - What code paths and contracts change.
- **Phases** - Recommended incremental slices.
- **Alternatives considered** - Briefly list rejected/deferred options.
- Affected modules (indicative):
  - `ppback/main.py`
  - `ppback/ppschema.py`
  - `ppback/db/ppdb_schemas.py`
  - `ppback/db/dbfuncs.py`
  - `alembic/versions/*` (if schema changes)
  - `pp_ascii/textualpp.py` (if client behavior changes)

## Auth and websocket compatibility

- Impact on `/token` flow and JWT payload assumptions.
- Impact on `/ws` token handshake and socket tracking.
- Backward compatibility expectations.

## Usability and documentation

- Docs to update (`README.md`, API docs, inline help, examples).
- Error messaging and discoverability implications.

## Testability

- Unit tests to add/update.
- API integration tests to add/update (`tests/test_api_users.py`,
  `tests/test_api_convs.py`, and `tests/conftest.py` when needed).
- Websocket flow validation strategy.
- Manual smoke checks (backend run + TUI run) if relevant.

## Complexity and rollout

- Estimated scope (S/M/L).
- Risk hotspots and dependencies.
- Rollout plan, feature flags, and rollback strategy (if applicable).

## A priori performance analysis

- Expected impact on hot paths:
  - Request latency
  - DB query count/index usage
  - Websocket fan-out/message handling
- Hypotheses only; include how you will validate post-implementation.

## Risks and open questions

- Known unknowns, correctness/security concerns, and unresolved decisions.

## Decision record

- **Status**: draft | proposed | accepted | superseded
- **Resolution**: fill once finalized.

## References

- Relevant code paths, issues, PRs, and prior evolution docs.
