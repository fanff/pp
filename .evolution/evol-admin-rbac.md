---
id: evol-admin-rbac
status: draft
created: 2026-05-14
authors: [franc]
related:
  - ppback/main.py
  - ppback/deps.py
  - ppback/db/ppdb_schemas.py
  - ppback/db/dbfuncs.py
  - ppback/init_db.py
  - ppback/ppschema.py
  - ppback/routers/users.py
  - tests/conftest.py
supersedes: []
superseded-by: ""
---

# Evolution: Admin RBAC — global admin flag and management API

## Summary

Add a global `is_admin` boolean to `UserInfo`, a `require_admin` FastAPI dependency guard, and four admin-only API endpoints for user and conversation management. The seed "admin" user automatically gets the flag. JWT payload stays unchanged — admin status is checked via DB on every admin-guarded request.

## Motivation and context

- **Current behavior**: The `init_db.py` seed creates a user named `"admin"` with zero special privileges. There is no way to promote a user, list all platform users, or manage conversation membership through any API. The only role concept is per-conversation (`ConvMember.role`) with no admin endpoint to modify it.
- **Problem**: No administrative API exists at all. Operating the platform requires direct DB access for basic tasks like viewing all users, changing a user's status, or adjusting conversation membership.
- **Why now**: The application needs a basic administrative capability to be operationally viable. Adding it now is inexpensive (single column, no JWT changes) and unblocks future admin features.
- **Constraints**: Auth flow (`/token` → JWT `{user_id}`), `decode_token` dep, and `/ws` handshake remain untouched. No new tables or many-to-many role models.

## Goals

1. Add `is_admin` boolean column to `UserInfo` (default `False`).
2. Add `require_admin` FastAPI dependency that queries the flag.
3. Expose four admin-only endpoints (list all users, promote/demote, list convs, change conv member role).
4. Update seed data so the `"admin"` user starts with `is_admin=True`.
5. Keep JWT payload, `/token`, and `/ws` handshake fully backward compatible.
6. Add test coverage for admin guard rejection and all four endpoints.

## Non-goals

- Many-to-many roles/permissions model — deferred to a future evolution if needed.
- Admin impersonation or acting-as-user endpoints.
- Conversation deletion, message moderation, or content muting — separate future work.
- Invite code management for other users — can be added later.
- Rate limiting or audit logging for admin actions — out of scope for this slice.

## User-visible functionality

### New endpoints

| Method | Route | Auth | Purpose |
|--------|-------|------|---------|
| `GET` | `/admin/users` | `require_admin` | List all users (id, name, nickname, is_admin, created_at) — no privacy filter |
| `POST` | `/admin/users/{user_id}/role` | `require_admin` | Set `is_admin` for a user (`{"is_admin": true/false}`) |
| `GET` | `/admin/conv` | `require_admin` | List all conversations (id, label, member count, created_at) |
| `POST` | `/admin/conv/{conv_id}/members/{user_id}/role` | `require_admin` | Change a user's per-conversation role (`{"role": "owner"|"admin"|"member"|"viewer"}`) |

### Breaking changes

None. All existing endpoints, auth flow, and WS protocol are unchanged.

### Additive changes

- `GET /admin/users` returns **all** users (unlike `GET /users` which is privacy-filtered).
- 403 response on any admin endpoint if the caller lacks `is_admin=True`.
- 404 on non-existent user/conv in admin endpoints.

## Technical approach

### Baseline (current)

- `UserInfo` has no admin column; admin check is impossible server-side.
- No admin router exists.
- `decode_token` returns `int user_id` only.

### Proposed change

**`ppback/db/ppdb_schemas.py`** — add column:
```python
class UserInfo(Base):
    ...
    is_admin: Mapped[bool] = mapped_column(Boolean, default=False)
```

**`ppback/deps.py`** — add guard:
```python
async def require_admin(
    current_user_id: Annotated[int, Depends(decode_token)],
    session: Annotated[AsyncSession, Depends(get_db)],
) -> int:
    user = await session.get(UserInfo, current_user_id)
    if not user or not user.is_admin:
        raise HTTPException(status_code=403, detail="Admin privileges required")
    return current_user_id
```

**`ppback/routers/admin.py`** — new router:
- `GET /admin/users` — `select(UserInfo).order_by(UserInfo.id)` → return all users
- `POST /admin/users/{user_id}/role` — validate user exists, set `is_admin`, commit
- `GET /admin/conv` — `select(Conv)` → for each, count members via `select(func.count()).select_from(ConvMember).where(...)`
- `POST /admin/conv/{conv_id}/members/{user_id}/role` — validate conv + user, update `ConvMember.role`, commit

**`ppback/main.py`** — register router:
```python
from ppback.routers import admin
app.include_router(admin.router)
```

**`ppback/init_db.py`** — set admin flag on seed:
```python
# after creating the "admin" user:
admin_user.is_admin = True
```

**Migration**: New Alembic revision adding `is_admin` column to `userinfo` table.

### Phases

Single phase — the scope is small and all changes are additive (no data migration, no index changes).

### Alternatives considered

- **JWT role claim** — rejected per user choice: requires re-login on role change, complicates the simple `decode_token` contract.
- **Separate `AdminRole` table** — unneeded for a single boolean; can be added later if more granular roles are needed.

### Affected modules

- `ppback/db/ppdb_schemas.py` — add `is_admin` column
- `ppback/deps.py` — add `require_admin` dependency
- `ppback/routers/admin.py` — new file, four endpoints
- `ppback/main.py` — register admin router
- `ppback/ppschema.py` — add schemas for admin request/response bodies
- `ppback/db/dbfuncs.py` — optionally add helper wrappers (or keep logic inline in router)
- `ppback/init_db.py` — set `is_admin=True` on seed admin user
- `alembic/versions/*` — new migration
- `tests/conftest.py` — seed an admin user in test fixture
- `tests/test_api_admin.py` — new test file for admin endpoints

## Auth and websocket compatibility

- `/token` output unchanged — JWT still has only `user_id`.
- `decode_token` unchanged.
- `require_admin` is a new `Depends()` that wraps `decode_token` + DB lookup.
- `/ws` handshake completely unaffected.
- No token refresh or re-login needed after promoting/demoting a user (DB-checked on every request).

## Usability and documentation

- `README.md` — add section documenting admin endpoints and authentication.
- Error messages: 403 with `"Admin privileges required"`, 404 for unknown user/conv.
- No new client-facing docs needed — admin API is server-side tooling.

## Testability

### Fixture updates (`tests/conftest.py`)

- Add a fourth user `"diana"` with `is_admin=True` to the seed data.
- Generate a `diana_token` for admin endpoint tests.

### New tests (`tests/test_api_admin.py`)

- `test_non_admin_gets_403` — bob/alice calls admin endpoint → 403.
- `test_admin_list_all_users` — diana calls `GET /admin/users` → sees all 4 users including herself.
- `test_admin_promote_user` — diana calls `POST /admin/users/{bob_id}/role` with `{"is_admin": true}` → bob can now call admin endpoints.
- `test_admin_demote_self` — diana demotes herself → subsequent admin calls return 403.
- `test_admin_list_all_convs` — diana calls `GET /admin/conv` → sees both seeded conversations.
- `test_admin_change_conv_role` — diana calls `POST /admin/conv/{id}/members/{bob_id}/role` with `{"role": "viewer"}` → bob can no longer write in that conversation.
- `test_admin_endpoint_404` — diana targets non-existent user/conv → 404.

### Manual smoke checks

- Run `python -m ppback.init_db`, login as `admin`/`admin`, hit `GET /admin/users` → confirms seed works.
- Promote/demote users via POST, verify effect on subsequent requests.

## Complexity and rollout

- **Scope**: S (~250 new lines of code: router, dep, schema changes, migration, tests).
- **Risk hotspots**: None significant — all changes are additive, no data migration risk, no existing behavior changes.
- **Rollout**: Single PR, merge when tests pass. No feature flags needed.
- **Rollback**: Revert the PR; `is_admin` column can be kept (defaults to False) or dropped in a follow-up.

## A priori performance analysis

| Hot path | Impact |
|----------|--------|
| `GET /admin/users` | One `SELECT` on `userinfo` table — negligible at expected scale |
| `POST /admin/users/{id}/role` | One `SELECT` + one `UPDATE` — negligible |
| `GET /admin/conv` | One `SELECT` on `conversations` + N `SELECT COUNT` queries (one per conv) — O(N) in conv count; fine at expected scale |
| `POST /admin/conv/{id}/members/{uid}/role` | Two `SELECT` + one `UPDATE` — negligible |
| Regular (non-admin) endpoints | Zero overhead — `require_admin` is never called |
| `/token`, `/ws` | Completely unaffected |

Hypothesis: Admin endpoints are infrequent operations (human-driven), so even O(N) queries per admin page load are acceptable. Validate by testing with 1000+ seeded conversations.

## Risks and open questions

- **Self-demotion**: Admin can demote themselves via the API, locking themselves out. Acceptable — another admin (or direct DB access) can restore. Document this.
- **Demoting the last admin**: Should we prevent demoting the last remaining admin? Not in v1 — document as an operational risk.
- **Migration ordering**: The Alembic migration must run before any admin endpoints are called. The `initialize_database_if_needed()` already runs `create_all` which will add the column for fresh DBs; migration handles existing DBs.

## Decision record

- **Status**: draft
- **Role model**: Single `is_admin` boolean on `UserInfo` (Q1: option 1).
- **Admin endpoints**: List all users, promote/demote, list convs, change conv member role (Q1: selected).
- **Admin auth mechanism**: DB lookup via `require_admin` Depends() on each request (Q2: option 1).
- **Conv membership API**: POST with JSON body setting role on an existing member (Q2: option 2).
- **JWT**: No changes.
- **Seed**: `"admin"` user gets `is_admin=True`.

## References

- [`ppback/db/ppdb_schemas.py`](../../ppback/db/ppdb_schemas.py) — `UserInfo` model to modify
- [`ppback/deps.py`](../../ppback/deps.py) — `decode_token` and `get_db` deps (pattern for `require_admin`)
- [`ppback/routers/users.py`](../../ppback/routers/users.py) — existing route patterns to follow
- [`ppback/main.py`](../../ppback/main.py) — router registration
- [`ppback/ppschema.py`](../../ppback/ppschema.py) — existing Pydantic models
- [`ppback/init_db.py`](../../ppback/init_db.py) — seed data
- [`tests/conftest.py`](../../tests/conftest.py) — fixture to extend
- `.evolution/evol-db-redesign.md` — prior evolution (deferred system-wide roles)
