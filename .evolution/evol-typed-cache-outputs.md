---
id: evol-typed-cache-outputs
status: draft
created: 2026-05-13
authors: [fanf, Claw]
related:
  - README.md
  - AGENTS.md
  - ppback/main.py
  - ppback/db/dbfuncs.py
  - ppback/db/ppdb_schemas.py
  - ppback/ppschema.py
  - tests/conftest.py
  - tests/test_api_users.py
  - tests/test_api_convs.py
supersedes: []
superseded-by: ""
---

# Evolution: Typed cache outputs and benchmark protocol

## Summary

PP currently uses in-memory caching through `fastapi-cache` in backend data helpers, but some cached results are observed as untyped dictionaries where callers expect typed objects. This evolution standardizes a typed cache contract for core helpers (`hook_user`, `membersof`, `allusers`, `get_conversation_list_for_user`), removes downstream fallback conversion code in API/ws paths once covered by tests, and defines a reproducible Locust benchmark protocol on fresh Docker Compose deployments with OpenTelemetry traces used for diagnosis.

## Motivation and context

- **Current behavior**
  - Cache backend is initialized in app lifespan with `InMemoryBackend` in `ppback/main.py`.
  - Data helpers in `ppback/db/dbfuncs.py` are decorated with `@cache(...)` and return a mix of typed objects and dictionaries.
  - `hook_user` is annotated as `UserInfo | None`, but `ppback/main.py` currently includes defensive `UserInfo.from_dict(...)` fallback in conversation creation and websocket auth flows.
  - Auth and ws flows (`/token`, `decode_token`, `/ws` first packet token handshake) are coupled and must remain stable.
- Problem or limitation in current behavior.
  - Cache return shape is not guaranteed to match function annotations, creating brittle call sites and hidden runtime type adaptation.
  - This weakens confidence in refactors and can hide cache serialization behavior changes.
- Why now.
  - Typed cache behavior is a foundational requirement before broad performance work and before treating cache results as reliable internal contracts.
  - A benchmark protocol is needed now so future cache changes are measured consistently on realistic deployment topology.
- Constraints from current architecture.
  - Keep `/token` response shape and JWT `user_id` payload compatibility.
  - Keep `/ws` auth handshake (`{"token": "..."}` as first message) unchanged.
  - Keep DB model and migration surface unchanged in this evolution.

## Goals

- Ensure cached helper outputs match declared return types at call sites.
- Remove `dict -> UserInfo` fallback logic from `ppback/main.py` after compatibility tests pass.
- Keep external API and websocket contracts backward compatible.
- Add test coverage proving typed cache behavior under warm-cache conditions.
- Establish a repeatable Locust + Docker Compose benchmark procedure with explicit pass/fail gates.

## Non-goals

- Replacing in-memory cache backend in this slice.
- Changing JWT payload shape, OAuth flow, or websocket handshake protocol.
- Redesigning DB schema, adding Alembic migrations, or changing conversation/message data model.
- Introducing distributed cache infrastructure (Redis, Memcached) in this evolution.

## User-visible functionality

- No intended user-facing API contract change.
- Behavioral impact is internal correctness and stability: backend code no longer needs fallback object reconstruction due to cache return type drift.


## Technical approach

- **Baseline**
  - Cached functions in `ppback/db/dbfuncs.py` can return dict-shaped data that is not always aligned with declared types.
  - `ppback/main.py` includes defensive conversions (`UserInfo.from_dict`) in both `/conv` creation path and `/ws` auth path.
- **Proposed change**
  - Define typed-output contract for cached helpers:
    - `hook_user(...) -> UserInfo | None`
    - `get_conversation_list_for_user(...) -> ConversationList`
    - `allusers(...) -> list[dict]` (explicitly dict-shaped and stable)
    - `membersof(...) -> list[dict]` (explicitly dict-shaped and stable)
  - For helpers expected to return ORM/Pydantic types, ensure cache encode/decode path preserves that type at function boundary.
  - Remove fallback object conversion in `ppback/main.py` once type-stability tests pass.
  - Keep cache key semantics stable unless a collision/incorrectness issue is found in tests.
- **Phases**
  - Phase A: Add type-focused tests around cached helper behavior (cold vs warm cache).
  - Phase B: Implement typed cache return normalization for typed helpers.
  - Phase C: Remove fallback conversion in `ppback/main.py` and run full API/ws regressions.
  - Phase D: Run benchmark campaign and record baseline vs candidate results.
- **Alternatives considered**
  - Keep fallback conversions forever: rejected because it masks correctness issues.
  - Replace cache backend now (Redis/distributed): deferred to later evolution.
  - Benchmark with in-process scripts only: rejected in favor of deployment-level load testing.
- Affected modules (indicative):
  - `ppback/main.py`
  - `ppback/db/dbfuncs.py`
  - `ppback/db/ppdb_schemas.py` (only if type helpers are refined)
  - `tests/conftest.py`
  - `tests/test_api_users.py`
  - `tests/test_api_convs.py`
  - `tests/` (new cache-type and ws/auth regression tests)
  - `benchmarks/` (new Locust scripts and runner docs/scripts)

## Auth and websocket compatibility

- `/token` output remains `{"access_token": "...", "token_type": "bearer"}`.
- JWT payload continues to include `user_id`; `decode_token` expectations remain unchanged.
- `/ws` handshake remains first-message JSON token packet; no protocol changes.
- Websocket socket-tracking behavior remains unchanged for this evolution.

## Usability and documentation

- Update `README.md` with benchmark section for compose-based runbook:
  - fresh build/start
  - seed/init conditions
  - Locust invocation
  - artifact locations
- Document benchmark interpretation:
  - Locust metrics are source of truth for pass/fail.
  - OTel traces are attribution and diagnostics only.

## Testability

- Unit/integration coverage to add or update:
  - Warm-cache typed return test for `hook_user` ensuring repeated calls return `UserInfo | None`.
  - Cache contract tests for `get_conversation_list_for_user` to preserve `ConversationList` shape.
  - Existing `/conv` and `/ws` paths exercised without `UserInfo.from_dict` fallback.
  - Regression tests for `/token`, `/users`, `/conv`, and `/ws` auth handshake remain green.
- Websocket flow validation:
  - valid token handshake remains accepted
  - invalid/missing/timeout handshake behavior unchanged

## Complexity and rollout

- Estimated scope: **M** (code + test + benchmark harness).
- Risk hotspots:
  - Incorrect cache deserialize behavior for typed objects.
  - Hidden dependencies on current dict fallback in websocket auth path.
  - Benchmark variability if environment is not reset between runs.
- Rollout plan:
  - Land tests first, then typed cache fixes, then fallback removal.
  - Run benchmark on baseline branch and candidate branch with same compose stack.
  - Merge only if correctness and benchmark gates pass.
- Rollback strategy:
  - Re-enable fallback conversion in `ppback/main.py` if production regressions appear.
  - Keep changes isolated to cache-contract paths for fast revert.

## A priori performance analysis

- Expected impact on hot paths:
  - Request latency for `/users` and `/conv` should improve or stay neutral on warm cache.
  - DB query count on warm hits should not increase; expected reduction/flat profile.
  - `/usermsg` write path may be neutral; guardrail allows small regression.
- Validation method (hypothesis-driven):
  - Compare baseline vs candidate with identical Locust scenario and fresh compose deploy.
  - Capture p50/p95 latency and error rates per endpoint.
  - Inspect trace spans (`allusers_db`, `get_conversation_list_for_user_db`, `hook_user_db`) to confirm expected hotspot movement.

### Benchmark protocol (Locust on fresh compose)

- Environment setup per run:
  - `docker compose -f compose.yml down -v`
  - `docker compose -f compose.yml build`
  - `docker compose -f compose.yml up -d`
  - wait for backend and postgres health; ensure fresh DB state before test start
- Traffic generator:
  - Locust scenario with 3 phases:
    - warmup: 2 minutes
    - steady: 8 minutes
    - spike: 2 minutes
  - mix: 70% reads (`GET /users`, `GET /conv`), 30% writes (`POST /usermsg`)
  - auth flow included (`/token`) and token reused per virtual user session
- Measurement and artifacts:
  - Primary: Locust stats (`p50`, `p95`, RPS, error rate) exported to JSON/CSV.
  - Secondary: OpenTelemetry traces exported through configured OTLP sink (Jaeger acceptable; ephemeral sink acceptable).
- Acceptance gates:
  - error rate `< 0.5%`
  - warm-cache `p95` regression for `GET /users` and `GET /conv` must not exceed `10%` vs baseline
  - warm-cache `p95` regression for `POST /usermsg` must not exceed `15%` vs baseline
- Reproducibility guardrails:
  - run baseline and candidate on same machine class and same compose file
  - no background load injection
  - same seeded data volume and same Locust parameters

## Risks and open questions

- `fastapi-cache` serialization path for ORM/Pydantic objects may require explicit encode/decode hooks.
- If typed cache normalization adds conversion overhead, warm-cache latency gains may be reduced.
- Open question: should typed-helper outputs be normalized to Pydantic models instead of ORM objects for stricter boundary control in future evolutions?

## Decision record

- **Status**: draft
- **Resolution**:
  - Entry mode: from scratch.
  - Target file: `.evolution/evol-typed-cache-outputs.md`.
  - Scope: typed cache outputs for current helper set, no auth/ws protocol changes.
  - Benchmark method: Locust deployment-level benchmark on fresh Docker Compose target.
  - Benchmark phases: 2m warmup, 8m steady, 2m spike.
  - Traffic mix: 70% read / 30% write.
  - Pass/fail thresholds accepted as defined in benchmark protocol.

## References

- `README.md`
- `AGENTS.md`
- `compose.yml`
- `ppback/main.py`
- `ppback/db/dbfuncs.py`
- `ppback/db/ppdb_schemas.py`
- `ppback/ppschema.py`
- `tests/conftest.py`
- `tests/test_api_users.py`
- `tests/test_api_convs.py`
