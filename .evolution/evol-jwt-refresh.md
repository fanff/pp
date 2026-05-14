---
id: evol-jwt-refresh
status: draft
created: 2026-05-14
authors: [opencode]
related: []
supersedes: []
superseded-by: ""
---

## Summary

Add JWT expiration and a refresh-token flow to PP Network. Access tokens
currently never expire — a leaked token is valid forever with no revocation
mechanism. This evolution introduces timed JWTs (1-hour `exp`), a
`refresh_tokens` DB table, and three new endpoints (`/token/refresh`,
`/token/revoke`, `/token/revoke-all`) so tokens are short-lived and can be
rotated or explicitly revoked.

## Motivation and context

- **Current behavior**: `POST /token` at `ppback/routers/users.py:65-68` calls
  `jwt.encode(payload={"user_id": ...})` with zero time-constrained claims.
  `decode_token` at `ppback/deps.py:34-41` calls `jwt.decode(..., verify=True)`
  which validates signature and algorithm but does **not** reject tokens
  lacking `exp`. A token stolen from localStorage, a log file, or a MITM
  attacker can be replayed indefinitely.
- **Problem**: No logout, no revocation, no session management. The only
  recourse is changing `MASTER_SECRET_KEY`, which invalidates **every** token
  globally — a sledgehammer approach.
- **Why now**: Security best practice, blocks basic product features (logout,
  device management), and is a contained 3-file change with zero breakage for
  existing clients.
- **Constraints**: Must keep backward compatibility with existing tokens
  (no `exp` → still accepted during a migration window). Must stay compatible
  with the `/ws` handshake (token sent as first JSON message).

## Goals

1. Access tokens carry an `exp` claim set to `utcnow + 1 hour`, validated on
   every `decode_token` call.
2. `POST /token` returns `access_token` + `refresh_token` + `token_type`.
3. `POST /token/refresh` accepts a refresh token, validates it, rotates it
   (issues a new refresh + access pair, marks old as revoked), and returns
   the new pair.
4. `POST /token/revoke` accepts a refresh token and marks it revoked.
5. `POST /token/revoke-all` (authenticated via Bearer token) revokes every
   refresh token belonging to the current user.
6. Backward-compatible: existing tokens without `exp` still work during a
   migration grace period.
7. All refresh token secrets are hashed (SHA-256) at rest — plaintext is never
   stored.

## Non-goals

- No device-tracking or session metadata beyond the `user_id` FK.
- No changes to the `/ws` handshake protocol (still sends `{"token": "..."}`).
- No rate-limiting on `/token` (deferred to a future evolution).
- No change to the admin router or `require_admin` dependency.
- No user-facing "sessions page" UI — that is a client concern.

## User-visible functionality

### Additive (no breaking changes)

| Endpoint | Method | Auth | Body | Response |
|----------|--------|------|------|----------|
| `/token/refresh` | POST | None | `{"refresh_token": "..."}` | `{"access_token", "refresh_token", "token_type"}` |
| `/token/revoke` | POST | None | `{"refresh_token": "..."}` | `{"status": "revoked"}` |
| `/token/revoke-all` | POST | Bearer | — | `{"revoked_count": N}` |

**Existing `/token` behavior changes**: the response now includes a
`refresh_token` field. Clients that ignore unknown fields (standard JSON
parser behavior) continue to work. Old tokens without `exp` continue to be
accepted — `decode_token` will only **require** `exp` after a documented
migration window (e.g. 2 releases).

## Technical approach

### Baseline flow (current)

```
POST /token (username + password)
  → validate password (bcrypt)
  → jwt.encode(payload={"user_id": N}, key=MASTER_SECRET_KEY)
  → return {"access_token": "<jwt>", "token_type": "bearer"}
```

No expiry, no refresh, no revocation.

### Proposed flow

```
POST /token (username + password)
  → validate password (bcrypt)
  → jwt.encode(payload={"user_id": N, "exp": now+1h}, key=MASTER_SECRET_KEY)
  → refresh_raw = secrets.token_urlsafe(32)
  → insert RefreshToken(user_id=N, token_hash=sha256(refresh_raw),
                         expires_at=now+30d)
  → return {"access_token": "<jwt>", "refresh_token": "<raw>",
            "token_type": "bearer"}

POST /token/refresh {"refresh_token": "<raw>"}
  → lookup by sha256(raw) where revoked=False AND expires_at > now
  → mark found row as revoked=True
  → issue new access_token + new refresh_token (same user)
  → return same shape as /token

POST /token/revoke {"refresh_token": "<raw>"}
  → lookup by sha256(raw)
  → set revoked=True
  → return {"status": "revoked"}

POST /token/revoke-all (Bearer <access_token>)
  → UPDATE refresh_tokens SET revoked=True WHERE user_id=decoded.sub AND revoked=False
  → return {"revoked_count": N}
```

### Phases

1. **Phase 1 — Core**: new `RefreshToken` model, Alembic migration,
   `create_tokens` + `refresh_token` + `revoke_token` helpers in
   `dbfuncs.py`, modified `/token` response, three new endpoints in a new
   `routers/auth.py` (or inline in `routers/users.py`).
2. **Phase 2 — Migration window**: add a log warning when a token without
   `exp` is used. After 2 releases, switch `decode_token` to
   `require=["exp"]`.
3. **Phase 3 — Polish** (optional, deferred): add `last_used_at` timestamp
   to `RefreshToken`, expose session list for admins.

### Alternatives considered

- **OPAQUE / PASETO instead of JWT**: unnecessary because JWT + refresh tokens
  are standard OAuth2 and all clients already speak `Authorization: Bearer`.
- **Server-side session store (Redis)**: adds operational complexity that is
  not justified for this project's scale. Refresh tokens in the application DB
  are sufficient.
- **Hard switch to require exp immediately**: would break every existing
  client token — unacceptable. A migration window is required.

### Affected modules

| Module | Change |
|--------|--------|
| `ppback/db/ppdb_schemas.py` | Add `RefreshToken` model |
| `ppback/db/dbfuncs.py` | Add `create_tokens`, `refresh_access_token`, `revoke_refresh_token`, `revoke_all_for_user` |
| `ppback/routers/users.py` | Modify `/token` response to include `refresh_token` |
| `ppback/routers/auth.py` **new** | Endpoints: `/token/refresh`, `/token/revoke`, `/token/revoke-all` |
| `ppback/ppschema.py` | Add `TokenRefreshIn`, `TokenRefreshOut`, `TokenRevokeIn`, `TokenRevokeAllOut` |
| `ppback/main.py` | Register `auth.router` |
| `ppback/deps.py` | Add optional `require=["exp"]` check (phase 2) |
| `alembic/versions/` | New migration for `refresh_tokens` table |
| `ppback/init_db.py` | No change needed (new table has no seed data) |

## Auth and websocket compatibility

- **`/token` response**: now includes `refresh_token` field. Clients that use
  `response["access_token"]` continue to work unchanged. No OAuth2 flow change
  (still `password` grant).
- **JWT payload**: the `user_id` claim is preserved. `decode_token` continues
  to return `int(user_id)`. The new `exp` claim is silently ignored by older
  clients (they never inspect JWT claims).
- **`/ws` handshake**: unchanged — first message is still `{"token": "<jwt>"}`.
  The WS handler never inspects the token payload beyond what `decode_token`
  returns, so `exp` has no effect on the handshake.
- **Backward compatibility**: tokens minted before this change lack `exp` but
  continue to pass `decode_token` because PyJWT's `verify=True` does not
  reject missing `exp` unless `options={"require": ["exp"]}` is set. We defer
  that option to phase 2.

## Usability and documentation

- **Error messages**: `POST /token` with bad credentials returns
  `400 "Incorrect username or password."` (unchanged). Expired access tokens
  return `401` from FastAPI's `OAuth2PasswordBearer` (auto-handled).
  `/token/refresh` with invalid/expired/revoked refresh token returns
  `401 "Invalid or expired refresh token."`.
- **Docs to update**: `README.md` — add the new endpoints to the API summary.
  No CHANGELOG update needed until release.

## Testability

### Unit / integration tests to add

| Test file | Tests |
|-----------|-------|
| `tests/test_api_users.py` | Fresh `/token` returns `refresh_token` field |
| `tests/test_api_users.py` | `/token/refresh` with valid token returns new pair and old token is revoked |
| `tests/test_api_users.py` | `/token/refresh` with revoked token returns 401 |
| `tests/test_api_users.py` | `/token/refresh` with expired token returns 401 |
| `tests/test_api_users.py` | `/token/revoke` marks token revoked, subsequent refresh 401s |
| `tests/test_api_users.py` | `/token/revoke-all` revokes all tokens for user, old tokens 401 on refresh |
| `tests/test_api_users.py` | Access token with `exp` still works for all existing endpoints |
| `tests/test_api_users.py` | Access token past `exp` returns 401 |

### Fixture changes

- `tests/conftest.py`: no structural change needed. The `client` fixture
  already calls `/token` for each user — the response will automatically
  include `refresh_token` on upgrade. Tests may want to capture it.

### Manual smoke check

```bash
# boot the server
uvicorn ppback.main:app --lifespan=on

# login — check refresh_token is present
curl -s -X POST http://localhost:8000/token \
  -d "username=admin&password=admin" \
  | python3 -m json.tool

# refresh — should get a new pair
# revoke — subsequent refresh should 401
```

## Complexity and rollout

- **Scope**: S (small) — ~150 lines of new code across 4-6 files, one new DB
  table, one new migration.
- **Risk hotspots**:
  - **Race on rotation**: If two concurrent `/token/refresh` calls use the
    same refresh token, the second will find the first already marked revoked
    and return 401. This is correct behavior and consistent with OAuth2
    best practices (refresh token rotation detects theft).
  - **Token collision**: `secrets.token_urlsafe(32)` produces 192 bits of
    entropy — collision probability is negligible.
- **Rollback**: revert the code change, drop the `refresh_tokens` table via
  Alembic downgrade. Clients lose the ability to refresh but existing access
  tokens continue to work until they expire naturally (max 1 hour).

## A priori performance analysis

- **`/token`**: one additional DB insert per login. No impact on existing
  endpoints.
- **`/token/refresh`**: 2 DB queries (select + update insert). Called
  infrequently (every ~55 min per client).
- **`/token/revoke`**: 1 DB update. Rare.
- **`/token/revoke-all`**: 1 bulk DB update. Extremely rare.
- **No impact on hot paths**: `/users`, `/conv`, `/usermsg`, `/ws` are
  completely unchanged.
- **Cache layer**: no cached functions are touched.

Hypothesis: total performance impact is negligible (< 0.1 ms per `/token`
call). Validate post-implementation by comparing `timeout 5` boot test
before and after.

## Risks and open questions

1. **Refresh token lifetime**: 30 days is the starting proposal. Should it be
   configurable via env var (`REFRESH_TOKEN_EXPIRY_DAYS`)? **Yes — add env var
   with a default of 30.**
2. **Migration window**: How long before we flip `require=["exp"]`? Suggestion:
   two releases (e.g. 2 months) with a warning log when an `exp`-less token
   is used.
3. **Test speed**: The monolitic `client` fixture rebuilds the DB per test.
   Adding 8 tests multiplies the runtime proportionally. Acceptable for now
   (adds ~3s) but worth optimizing in a separate evolution.

## Decision record

- **Status**: draft
- **Resolution**: —

## References

- `ppback/routers/users.py:37-69` — current `/token` implementation
- `ppback/deps.py:33-41` — current `decode_token` implementation
- `ppback/deps.py:44-51` — `require_admin` dependency (unchanged)
- `ppback/config.py:14` — `MASTER_SECRET_KEY` env var
