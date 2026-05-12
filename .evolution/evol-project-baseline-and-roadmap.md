---
id: evol-project-baseline-and-roadmap
status: draft
created: 2026-05-12
authors: [fanf, Claw]
related:
  - README.md
  - AGENTS.md
  - ppback/main.py
  - ppback/ppschema.py
  - ppback/db/ppdb_schemas.py
  - ppback/db/dbfuncs.py
  - pp_ascii/textualpp.py
supersedes: []
superseded-by: ""
---

# Evolution: PP project baseline and roadmap

## Summary

PP Network is currently a compact conversational backend with password login, JWT-protected HTTP endpoints, conversation membership, message persistence, websocket fan-out, and a Textual TUI client. This evolution document captures the current project baseline and proposes an incremental roadmap for making PP easier to extend, test, and operate without breaking the existing `/token`, `/conv`, `/usermsg`, and `/ws` contracts.

## Motivation and context

- **Current behavior**
  - `ppback/main.py` exposes the FastAPI app, `/token`, `/users`, `/conv`, `/conv/{conversation_id}/messages`, `/usermsg`, and `/ws`.
  - Auth uses OAuth2 password login at `/token`; JWT payloads currently contain `user_id` and are decoded by `decode_token`.
  - Conversation membership is enforced through `ConvPrivacyMembers` checks before message reads and writes.
  - Messages are stored as `ConvoMessage` rows plus `Convchanges` rows, then broadcast to connected users through the current in-process socket registry.
  - The websocket endpoint accepts the socket first, then expects a token-bearing first message within 5 seconds.
  - Current websocket event payloads are not yet shaped as durable resync hints; this should be fixed before deeper fan-out changes.
  - The Textual client uses `PPN_HOST` and `PPN_WSHOST`, calls HTTP endpoints through `PPClient`, and listens for websocket messages.
- **Problem or limitation**
  - The code works as a prototype, but several project TODOs and rough edges need a shared direction before implementation: bot participation, fixed user colors, admin user management, DB initialization/migration clarity, websocket/auth hardening, and stronger tests.
  - Tests currently cover basic `/users` and `/conv` behavior, but not message posting, message history, websocket auth, websocket fan-out, or websocket event contract regressions.
  - DB initialization can happen on app import if the app cannot query `UserInfo`, which is convenient locally but risky when pointed at non-local databases.
- **Why now**
  - Before adding agents/bots or richer clients, PP needs a stable documented baseline so future changes can be split into small, test-backed evolutions.
- **Constraints from current architecture**
  - `/token` output and `decode_token` payload assumptions must remain compatible unless clients are updated together.
  - `/ws` currently relies on a first-message token handshake; clients and tests must stay aligned with that behavior.
  - Schema changes need SQLAlchemy model updates, Alembic migrations, seed/init updates, and fixture changes.
  - TUI behavior is coupled to current HTTP and websocket contracts.

## Goals

- Establish a shared baseline for PP’s current architecture and behavior.
- Define an incremental roadmap that can be implemented through small, reviewable evolutions.
- Keep existing user-visible behavior working while improving reliability, test coverage, and extensibility.
- Make future bot/user/conversation work explicit about API, DB, websocket, TUI, and test impacts.
- Add enough validation around the core flows that regressions are caught before larger features land.

## Non-goals

- Rewriting PP into a different framework or architecture.
- Replacing FastAPI, SQLAlchemy, Alembic, Textual, or the current websocket approach in one large change.
- Designing the full bot runtime in this baseline document.
- Changing the JWT payload, `/token` response shape, or websocket handshake without a dedicated compatibility plan.
- Changing client/TUI behavior as part of the first websocket cleanup slice; the first slice is backend-only.
- Moving dependency management away from `uv` unless a later evolution explicitly chooses that.

## User-visible functionality

This baseline evolution should not directly change user-visible behavior. It proposes documentation and planning work first, followed by additive implementation slices.

Expected future user-visible improvements:

- More reliable conversation and message behavior.
- Clearer errors for auth, membership, and message-posting failures.
- A path toward bot users joining conversations.
- Stable user colors/nicknames in clients.
- Optional admin APIs for user management.
- Better local/dev instructions and smoke checks.

Compatibility expectations:

- Existing login credentials and `/token` clients should keep working.
- Existing TUI configuration via `PPN_HOST` and `PPN_WSHOST` should keep working.
- Existing websocket first-message auth should keep working until a specific replacement is designed and migrated.

## Technical approach

### Baseline

The current core flow is:

1. A user logs in through `/token` with OAuth2 form data.
2. The server signs a JWT containing `user_id`.
3. HTTP endpoints use `Depends(decode_token)` to obtain the current user id.
4. Conversation access is checked through `ConvPrivacyMembers`.
5. `/usermsg` writes a `ConvoMessage` and matching `Convchanges` row.
6. Connected users are tracked in memory and receive websocket broadcasts.
7. Clients fetch conversation lists and history over HTTP, then receive live updates over websocket.

### Proposed change

Use this document as the top-level roadmap, then split implementation into focused follow-up evolutions:

1. **Core regression coverage**
   - Add tests for `/token`, `/usermsg`, `/conv/{id}/messages`, unauthorized access, and invalid conversation membership.
   - Add websocket handshake/fan-out tests where feasible.
2. **Backend websocket event/resync contract**
   - Evolve the websocket message structure first so every live event can be used as a resync hint.
   - Keep the change backend-only: no TUI/client feature work in this slice beyond preserving existing compatibility.
   - Prefer typed event payloads, for example `message.created`, carrying conversation id, change id, message id, sender id, and timestamp/watermark, but not message content.
   - Pair websocket control events with an HTTP history resync contract based on `after=<last_seen_change_id>` for each conversation.
   - Define `after` as an exclusive monotonic `Convchanges.id` cursor, not a wall-clock timestamp.
3. **Fan-out cleanup**
   - Remove in-memory fan-out entirely as part of this cleanup, not merely hide it behind an interface.
   - Use Postgres `LISTEN`/`NOTIFY` as the first shared fan-out transport.
   - Treat websocket delivery as best-effort control-plane signaling; HTTP history remains the source of truth for message content and resync.
4. **DB initialization and migration clarity**
   - Decide how dev auto-init, Alembic migrations, and production startup should interact.
   - Avoid surprising schema creation/modification when pointing at real databases.
5. **Conversation/user experience polish**
   - Define fixed user colors and where they live: DB column, deterministic client-side mapping, or config.
   - Clarify nickname/name display rules across API and TUI.
6. **Admin/user management APIs**
   - Design add/list/update/deactivate user flows and required roles.
   - Keep backward compatibility for normal users.
7. **Bot participation**
   - Decide whether bots are normal users, service identities, or a separate entity.
   - Define how bots join conversations, receive messages, and send messages.
8. **Client and docker hardening**
   - Keep TUI and docker env examples aligned with backend contracts.
   - Add smoke checks for local backend + TUI usage.

### Phases

- **Phase 0: Baseline doc** — land this draft and refine priorities.
- **Phase 1: Message/event contract** — evolve backend websocket events into durable resync hints while preserving existing endpoint compatibility.
- **Phase 2: Fan-out cleanup** — remove in-memory fan-out and implement Postgres `LISTEN`/`NOTIFY` for shared control-plane websocket signaling.
- **Phase 3: Safety net expansion** — expand tests around auth, conversations, messages, websocket auth, fan-out, and history recovery.
- **Phase 4: Operational cleanup** — clarify DB initialization/migrations and local/docker docs.
- **Phase 5: UX/API polish** — fixed user colors, better errors, admin API design.
- **Phase 6: Bot evolution** — design and implement bot conversation participation.

### Alternatives considered

- **Large rewrite first** — rejected because the current project is small enough to evolve incrementally.
- **Bot feature first** — deferred until message/websocket/auth regression coverage is stronger.
- **Client-only polish first** — useful, but it risks hiding backend contract gaps rather than fixing them.

### Affected modules

Likely affected by later implementation evolutions:

- `ppback/main.py`
- `ppback/ppschema.py`
- `ppback/db/ppdb_schemas.py`
- `ppback/db/dbfuncs.py`
- `ppback/init_db.py`
- `alembic/versions/*`
- `ppback/wsocket.py`
- `ppback/apiclient.py`
- `pp_ascii/textualpp.py`
- `tests/conftest.py`
- `tests/test_api_users.py`
- `tests/test_api_convs.py`
- new message/websocket/admin tests

## Auth and websocket compatibility

- `/token` should continue returning `{"access_token": "...", "token_type": "bearer"}`.
- JWTs should continue containing `user_id` until a migration plan exists.
- HTTP endpoints should keep using bearer auth unless a dedicated auth evolution changes that.
- `/ws` currently accepts the socket, waits up to 5 seconds, then expects token-bearing JSON. This must remain compatible with current clients or be migrated deliberately.
- Websocket tokens must not be logged; log authenticated user id, socket id, and auth outcome instead.
- Websocket events should be shaped as typed backend control events that can drive resync, starting with message creation.
- Message content should not be part of websocket events; clients should fetch message history/details over HTTP using `after=<last_seen_change_id>` per conversation.
- Fan-out should be routed through a named backend component backed by Postgres `LISTEN`/`NOTIFY` rather than endpoint code directly managing socket storage.
- The first fan-out replacement should support multi-process operation by design through the database notification channel.

## Usability and documentation

Documentation updates to consider:

- Refresh `README.md` with current `uv` setup, backend run, DB init, TUI run, and docker compose flow.
- Document default dev users and clarify that they are development-only.
- Add short API usage examples for login, list conversations, post message, fetch history with `after=<last_seen_change_id>`, and websocket subscribe.
- Document operational expectations for SQLite dev mode vs Postgres compose mode.
- Keep TUI env vars (`PPN_HOST`, `PPN_WSHOST`) visible and current.

## Testability

Near-term test plan:

- Add `/token` success and failure tests.
- Add `/usermsg` success test and verify message appears in `/conv/{id}/messages`.
- Add unauthorized message post/read tests for users outside a conversation.
- Add invalid conversation/user id tests for conversation creation and message posting.
- Add websocket auth handshake tests:
  - valid token connects and stays available;
  - missing/invalid token closes;
  - timeout closes.
- Add websocket event-shape tests confirming message events include enough data to trigger `after=<last_seen_change_id>` history resync: event type, conversation id, change id, message id, sender id, and timestamp/watermark, but not message content.
- Add history resync tests for `/conv/{conversation_id}/messages?after=<last_seen_change_id>`, where `after` is an exclusive `Convchanges.id` cursor.
- Add websocket fan-out test for sending a message to members.
- Add stale/dead socket cleanup tests for fan-out send failures where feasible.
- Update `tests/conftest.py` as needed so fixtures are isolated, deterministic, and do not leak state.

Manual smoke checks:

```bash
uv sync
python -m ppback.init_db
uvicorn ppback.main:app --reload
```

Then, in another shell:

```bash
export PPN_HOST="http://localhost:8000/"
export PPN_WSHOST="ws://localhost:8000/"
python -m pp_ascii.textualpp
```

## Complexity and rollout

- Estimated scope: **M** overall, but each phase should be **S**.
- Risk hotspots:
  - Auth changes breaking both HTTP and websocket clients.
  - DB model changes without matching Alembic migrations or fixture updates.
  - Websocket behavior changes that the TUI or Godot/web clients cannot follow.
  - FastAPI app import side effects when pointed at real databases.
- Rollout plan:
  - Land docs and tests first.
  - Implement one behavior slice per branch/evolution.
  - Keep compatibility unless a migration is explicit.
- Rollback strategy:
  - Prefer additive DB changes.
  - Keep old response fields while adding new fields when possible.
  - Feature-gate larger bot/admin behavior if it affects existing clients.

## A priori performance analysis

Expected hot paths:

- `/conv` currently loads conversation membership per conversation; this may become query-heavy as conversation count grows.
- `/usermsg` performs membership checks, writes two rows, reads members, and then emits a backend fan-out event after commit.
- The first fan-out replacement should not use in-memory process-local delivery; it should use Postgres `LISTEN`/`NOTIFY`.
- Websocket delivery is best-effort control signaling; clients must recover message content and missed events through HTTP message history.
- Caching in `dbfuncs.py` may reduce repeated reads, but cache invalidation needs care when users, memberships, or conversations change.

Validation ideas after implementation work:

- Count DB queries for `/conv`, `/usermsg`, and message history.
- Time message post-to-websocket receive latency in local smoke tests.
- Add a small benchmark around batch message sends only after correctness tests are reliable.

## Risks and open questions

- Should bots be represented as normal `UserInfo` rows, a separate table, or service identities attached to users?
- Should fixed user colors be stored in the DB or generated deterministically in clients?
- Should DB initialization remain automatic on app import, or move to explicit init/migration commands only?
- What authorization model should admin APIs use: hard-coded admin users, role column, conversation roles, or a separate permissions model?
- What exact event schema is the minimum durable resync contract for message creation, including the required `change_id` cursor?
- How should clients initialize and persist each conversation's `last_seen_change_id` cursor?
- How should Postgres notification payloads be versioned and kept below payload limits?
- What minimum multi-process websocket behavior must be proven in tests or smoke checks?
- Should websocket auth move back toward headers when clients support it, or keep the first-message handshake permanently for compatibility?

## Decision record

- **Status**: draft
- **Resolution**: Initial baseline created. First websocket cleanup direction: backend-only event/resync contract, no message content in websocket events, and Postgres `LISTEN`/`NOTIFY` as the shared fan-out transport.

## References

- `README.md`
- `AGENTS.md`
- `SKILL.md`
- `.opencode/skills/evol/SKILL.md`
- `ppback/main.py`
- `ppback/ppschema.py`
- `ppback/db/ppdb_schemas.py`
- `ppback/db/dbfuncs.py`
- `ppback/wsocket.py`
- `ppback/apiclient.py`
- `pp_ascii/textualpp.py`
- `tests/conftest.py`
- `tests/test_api_users.py`
- `tests/test_api_convs.py`
