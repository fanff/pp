---
id: evol-db-redesign
status: draft
created: 2026-05-13
authors: []
related: []
supersedes: []
superseded-by: ""
---

# Evolution: Database redesign with RBAC and privacy

## Summary

Redesign the PP Network database schema to eliminate the indirect `Convchanges` bridge table, introduce conversation-level RBAC (owner/admin/member/viewer), add a friendship-based privacy system with invite codes, and prepare for future rich message types — all while keeping the `/token` auth and `/ws` handshake untouched.

## Motivation and context

- **Current behavior**: `ConvoMessage` has no direct foreign key to `Conv`. Messages are linked to conversations through the `Convchanges` bridge table (`conversations` ← `convchanges` → `convomessage`), requiring a mandatory JOIN on every message query (`messaging.py:91-104`). The `Convchanges.change_type` column only ever holds `"message"` — the polymorphic indirection is unused overhead.
- **Problem**: Every message read/write traverses two tables instead of one. There is no permission system beyond membership checks (`user_allowed_in_convo` in `dbfuncs.py:149`). There is no message typing (all content is plain text). Users are globally discoverable via `GET /users`.
- **Why now**: The current layout blocks every upcoming feature — rich messages, typing indicators, privacy controls. Fixing the foundation first avoids compounding tech debt.
- **Constraints**: Auth flow (`/token` → JWT `user_id` payload), `decode_token` dep, and `/ws` token handshake must remain unchanged. Existing Alembic migrations need a squash or new baseline migration.

## Goals

1. Direct `conversation_id` FK on `ConvoMessage` — eliminate the `Convchanges` JOIN for message queries.
2. Conversation-level RBAC with roles: `owner`, `admin`, `member`, `viewer` — enforced at write endpoints.
3. Friendship system: invite-code-based friend requests + acceptance flow; friends auto-quality for 1:1 conversations.
4. Privacy-aware user discovery: `GET /users` returns only friends, shared-conversation peers, and pending request senders.
5. Message type support: `message_type` enum column + `payload` JSON column on `ConvoMessage` for type-specific data (image URLs, audio metadata, custom component props).
6. Standardized `created_at` timestamps on core tables.

## Non-goals

- System-wide roles (superadmin, moderator, etc.) — deferred.
- Typing indicators, message editing/deletion — separate future evolution.
- Media upload/storage service — out of scope for DB schema redesign.
- Dropping the unused `ConvStartingPoint` and conversation `parent_id`/`parent_ts` columns — harmless; clean up separately.

## User-visible functionality

### Breaking changes

- `GET /users` no longer returns all platform users — only mutual contacts (friends, conversation peers, request senders).
- `GET /conv/{id}/messages` response shape changes: `change_id` and `message_id` fields collapse into `id` (since the Convchanges cursor disappears). The `after` cursor now refers to `ConvoMessage.id`.
- `POST /usermsg` response no longer returns `change_id` in the same sense; returns `message_id` only.

### Additive changes

| Endpoint | Method | Purpose |
|----------|--------|---------|
| `/invite-codes` | POST | Generate a one-time invite code |
| `/friend-requests` | POST | Submit invite code → create friend request |
| `/friend-requests` | GET | List pending requests (incoming + outgoing) |
| `/friend-requests/{id}/accept` | POST | Accept pending request → establish friendship |
| `/friend-requests/{id}/reject` | POST | Reject pending request |
| `/friends` | GET | List friends |

### Migration notes

Clients currently using `change_id` for cursor-based pagination must switch to `ConvoMessage.id`. The `/ws` push event drops `change_id` and `message_id` in favor of a single `message_id` cursor.

## Technical approach

### Baseline (current)

```
Conv ──1:N── Convchanges ──N:1── ConvoMessage
  │                              │
  └──1:N── ConvPrivacyMembers    └──N:1── UserInfo
```

Every message read: `Convchanges JOIN ConvoMessage WHERE conv_id = ?`
Every message write: INSERT into `ConvoMessage`, INSERT into `Convchanges`, COMMIT.

### Proposed schema

```
Conv ──1:N── ConvoMessage ──N:1── UserInfo
  │            │
  │            └── message_type: str (text|image|audio|custom)
  │            └── payload: JSON (nullable, type-specific data)
  │
  └──1:N── ConvMember (renamed from ConvPrivacyMembers, role field refined)

UserInfo ──1:N── InviteCode
UserInfo ──1:N── FriendRequest (from_user / to_user)
UserInfo ──N:M── Friendship (symmetric, user_a_id < user_b_id)
```

### Affected modules

- `ppback/db/ppdb_schemas.py` — add models, drop Convchanges, rename ConvPrivacyMembers → ConvMember
- `ppback/db/dbfuncs.py` — rewrite `create_convo`, `get_conversation_list_for_user`, `user_allowed_in_convo`; add friendship/invite helpers
- `ppback/routers/messaging.py` — remove Convchanges JOINs, simplify message queries, enforce RBAC
- `ppback/routers/users.py` — privacy-aware `GET /users`, add invite/friend endpoints
- `ppback/ppschema.py` — add schemas for friend requests, invite codes, message type extensions
- `ppback/wsocket.py` — `MessageWS` schema drops `change_id`, keeps `message_id` as cursor
- `alembic/versions/*` — new baseline migration (squash or new migration dropping Convchanges, adding columns)
- `ppback/init_db.py` — seed admin/user with proper roles

### New table definitions (indicative)

```python
class ConvoMessage(Base):
    __tablename__ = "convomessage"
    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    conv_id: Mapped[int] = mapped_column(ForeignKey("conversations.id"), index=True)
    sender_id: Mapped[int] = mapped_column(ForeignKey("userinfo.id"), index=True)
    ts: Mapped[float] = mapped_column(Float, index=True)
    message_type: Mapped[str] = mapped_column(String, default="text", index=True)
    content: Mapped[str] = mapped_column(String)
    payload: Mapped[str | None] = mapped_column(String, nullable=True)

class ConvMember(Base):
    __tablename__ = "conv_members"
    __table_args__ = (UniqueConstraint("conv_id", "user_id", name="conv_user_uc"),)
    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    conv_id: Mapped[int] = mapped_column(ForeignKey("conversations.id"))
    user_id: Mapped[int] = mapped_column(ForeignKey("userinfo.id"))
    role: Mapped[str] = mapped_column(String, default="member")

class InviteCode(Base):
    __tablename__ = "invite_codes"
    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    code: Mapped[str] = mapped_column(String, unique=True, index=True)
    creator_id: Mapped[int] = mapped_column(ForeignKey("userinfo.id"))
    status: Mapped[str] = mapped_column(String, default="active")
    created_at: Mapped[float] = mapped_column(Float)

class FriendRequest(Base):
    __tablename__ = "friend_requests"
    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    from_user_id: Mapped[int] = mapped_column(ForeignKey("userinfo.id"))
    to_user_id: Mapped[int] = mapped_column(ForeignKey("userinfo.id"))
    invite_code_id: Mapped[int | None] = mapped_column(ForeignKey("invite_codes.id"), nullable=True)
    status: Mapped[str] = mapped_column(String, default="pending")

class Friendship(Base):
    __tablename__ = "friendships"
    __table_args__ = (UniqueConstraint("user_a_id", "user_b_id", name="friendship_uc"),)
    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    user_a_id: Mapped[int] = mapped_column(ForeignKey("userinfo.id"))
    user_b_id: Mapped[int] = mapped_column(ForeignKey("userinfo.id"))
    created_at: Mapped[float] = mapped_column(Float)
```

### Phases

**Phase 1 — Schema cleanup (small, testable)**
- Add `conv_id`, `ts`, `message_type`, `payload` columns to `ConvoMessage`.
- Migrate data: for each `Convchanges` row with `change_type="message"`, copy `conv_id` and `ts` to the linked `ConvoMessage`.
- Drop `Convchanges` table and model.
- Update `GET /conv/{id}/messages` to query `ConvoMessage` directly.
- Update `POST /usermsg` to write to `ConvoMessage` only.

**Phase 2 — RBAC (medium, preserves existing semantics)**
- Add `created_at` to `Conv` and `UserInfo`.
- Rename `ConvPrivacyMembers` to `ConvMember`; refine `role` column with constraints (owner/admin/member/viewer).
- Add RBAC guard to `POST /usermsg` (owner/admin/member can write; viewer cannot).
- Seed data in `init_db.py` sets conversation creator as `owner`.

**Phase 3 — Privacy + friends (medium, additive)**
- Add `InviteCode`, `FriendRequest`, `Friendship` tables.
- Add invite code generation endpoint.
- Add friend request + accept/reject endpoints.
- Add list friends endpoint.
- Rewrite `GET /users` to filter by friendship + shared-conv membership.
- Update fixture in `tests/conftest.py` to seed relationships.

### Alternatives considered

- **Keeping Convchanges as event log**: more tables to maintain; no concrete non-message events yet. Merge now, re-add as event log when typing indicators land.
- **Separate tables per message type**: normalized but increases query complexity. Prefer single table with typed `payload` JSON.
- **System-wide roles**: out of scope for conversation-level RBAC.

## Auth and websocket compatibility

- `/token` → JWT {user_id} unchanged. `decode_token` unchanged.
- `/ws` handshake (token JSON within 5s) unchanged. Socket tracking (`InMemSockets`) unchanged.
- `MessageWS` push event drops the `change_id` field; `message_id` is the new cursor. Client must update parsing.

## Usability and documentation

- `README.md` — add note about privacy-aware user discovery.
- API docs will auto-update via Pydantic schemas for new endpoints.
- Error messaging: 403 when a viewer tries to write; 404 when accessing unknown/non-member users.

## Testability

### Fixture updates (`tests/conftest.py`)

- Seed `InviteCode`, `FriendRequest`, `Friendship` records alongside existing users and conversations.
- Assign `owner` role to conversation creators.

### Phase 1 tests

- `test_get_messages_no_convchanges_join` — verify messages load via `ConvoMessage` directly.
- `test_post_message_only_writes_convo_message` — verify only one INSERT on write.

### Phase 2 tests

- `test_viewer_cannot_write` — user with `viewer` role gets 403 on `POST /usermsg`.
- `test_owner_can_remove_members` — owner can delete member; member cannot.

### Phase 3 tests

- `test_invite_code_create_and_use` — generate code, submit, verify friend request created.
- `test_friend_request_accept` — accept creates friendship, both users appear in `/friends`.
- `test_users_hidden_from_non_friends` — verify `/users` doesn't leak non-relation users.
- `test_friends_can_create_1_to_1_conversation` — two friends create a direct conv.

### Manual smoke checks

- Run `uvicorn ppback.main:app --reload`, create users, exchange invite codes, verify `/users` isolation.
- Verify existing messages survive migration by comparing pre/post message lists.

## Complexity and rollout

- **Scope**: L (3 phases, ~4-5 new endpoints, schema migration, fixture overhaul).
- **Risk hotspots**: Data migration accuracy (Phase 1), RBAC enforcement gaps (Phase 2), privacy leak edge cases (Phase 3).
- **Rollout**: Deploy phase-by-phase. Each phase is independently testable via `pytest`. No feature flags proposed — the schema changes are breaking and best done as a coordinated migration.
- **Rollback**: Keep a pre-migration DB dump. Phase 1 migration is reversible (add columns, copy data, then drop Convchanges as final step).
- **Dependencies**: Phase 2 and 3 both depend on Phase 1.

## A priori performance analysis

| Hot path | Before | After | Change |
|----------|--------|-------|--------|
| `GET /conv/{id}/messages` | 1 JOIN (Convchanges → ConvoMessage) | Direct `WHERE conv_id = ?` | **-1 JOIN per request**, ~2x faster on SQLite, significant on Postgres at scale |
| `POST /usermsg` | 2 INSERTs + 2 FLUSHes + 2 REFRESHs | 1 INSERT + 1 FLUSH + 1 REFRESH | **-50% write overhead** |
| `GET /users` | 1 SELECT (all users) | 1-2 SELECTs (friends + conv peers) | **Slower** for small user counts, **much faster** at scale (no full table scan) |
| WS broadcast | Same per-user socket fan-out | No change | No impact |

Hypothesis: Phase 1 eliminates the single biggest query tax. Validate with `EXPLAIN ANALYZE` on Postgres before/after migration.

## Risks and open questions

- **Data migration**: Must ensure no `Convchanges` row is orphaned. A `Convchanges` with `change_type != "message"` would be lost — audit the DB before migrating.
- **1:1 conversation creation**: Should accept-friendship auto-create a 1:1 conv, or create lazily on first message? Proposed: lazy (no conv until the first message between friends), simpler and avoids ghost conversations.
- **Invite code expiry**: One-time use + TTL? Proposed: one-time use only; no TTL for v1.
- **Rate limiting**: Invite code generation and friend request submission should be rate-limited per user to prevent spam.
- **RBAC enforcement granularity**: v1 enforces write permission only. Future evolutions can add member management, conversation deletion, etc.

## Decision record

- **Status**: draft
- **Convchanges fate**: Merge into ConvoMessage (Q1: option 1).
- **RBAC scope**: Conversation-level only (Q2: option 1).
- **Message type model**: Enum + indexed columns + JSON payload (Q6).
- **Privacy system**: Invite-code-based friend requests + acceptance (Q5: option 1).

## References

- [`ppback/db/ppdb_schemas.py`](../../ppback/db/ppdb_schemas.py) — current models to modify
- [`ppback/db/dbfuncs.py`](../../ppback/db/dbfuncs.py) — helpers to rewrite
- [`ppback/routers/messaging.py`](../../ppback/routers/messaging.py) — Convchanges JOIN queries
- [`ppback/ppschema.py`](../../ppback/ppschema.py) — MessageWS watermark field references Convchanges.id
- [`ppback/routers/ws.py`](../../ppback/routers/ws.py) — websocket handshake (unchanged)
- [`tests/conftest.py`](../../tests/conftest.py) — fixture to extend
- `.evolution/evol-route-split.md` — prior evolution (style reference)
