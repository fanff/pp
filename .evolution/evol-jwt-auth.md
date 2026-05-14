---
id: evol-jwt-auth
status: draft
created: 2026-05-14
authors: [opencode]
related: []
supersedes:
  - evol-jwt-refresh
  - evol-jwt-security
superseded-by: ""
---

## Summary

Overhaul PP Network's JWT authentication system: add expiration, refresh-token
rotation with revocation, standard JWT claims (`iat`, `sub`), and include user
profile fields (`user_id`, `name`, `nickname`, `is_admin`) directly in the
`/token` response. Access tokens currently never expire and carry no metadata
— a leaked token is valid forever, every client needs a separate API call to
get the current user's info, and the JWT lacks standard audit claims. This
evolution introduces timed JWTs (1-hour `exp`), a `refresh_tokens` DB table,
three new endpoints, and enriched `/token` response — all backward-compatible
with existing clients.

## Motivation and context

- **Current behavior**: `POST /token` at `ppback/routers/users.py:65-68` calls
  `jwt.encode(payload={"user_id": ...})` with zero time-constrained or standard
  claims. `decode_token` at `ppback/deps.py:34-41` calls `jwt.decode(..., verify=True)`
  which validates signature and algorithm but does **not** reject tokens lacking
  `exp`, `iat`, or `sub`. A token stolen from localStorage, a log file, or a
  MITM attacker can be replayed indefinitely.
- **Problems**:
  1. **No expiry**: A leaked token is valid forever — no logout, no revocation,
     no session management. The only recourse is changing `MASTER_SECRET_KEY`,
     which invalidates **every** token globally.
  2. **Extra round-trips**: Every client that needs the current user's name,
     nickname, or admin status must issue a separate API call (e.g. `GET /users`).
  3. **No standard claims**: The JWT lacks `iat` (issued-at) and `sub`
     (subject), making audit, debugging, and token introspection harder. Missing
     `iat` also means no anchor point for determining token age.
  4. **Auth in `users.py`**: The `/token` endpoint is mixed into the users
     router alongside friend requests and invite codes — a separation-of-concerns
     smell.
- **Why now**: Security best practice, enables basic product features (logout,
  device management), reduces client HTTP overhead, and is a contained set of
  additive changes with zero breakage for existing clients.
- **Constraints**: Must keep backward compatibility with existing tokens
  (no `exp`/`iat`/`sub` → still accepted during a migration window). Must stay
  compatible with the `/ws` handshake (token sent as first JSON message).

## Goals

1. Access tokens carry an `exp` claim set to `utcnow + 1 hour`, validated on
   every `decode_token` call.
2. JWT payload gains `iat` (UTC epoch seconds at issuance) and `sub` (user_id
   as string, per RFC 7519 §4.1.2).
3. `POST /token` returns `access_token` + `refresh_token` + `token_type` +
   `user_id` + `name` + `nickname` + `is_admin`.
4. `POST /token/refresh` accepts a refresh token, validates it, rotates it
   (issues a new refresh + access pair, marks old as revoked), and returns
   the new pair (including user info fields).
5. `POST /token/revoke` accepts a refresh token and marks it revoked.
6. `POST /token/revoke-all` (authenticated via Bearer token) revokes every
   refresh token belonging to the current user.
7. Backward-compatible: existing tokens without standard claims still work
   during a documented migration window (warning logged, hard `require` option
   deferred by 2 releases).
8. All refresh token secrets are hashed (SHA-256) at rest — plaintext is never
   stored.
9. (Optional) Extract `/token` and all token-management endpoints into a
   dedicated `routers/auth.py` for separation of concerns.

## Non-goals

- No device-tracking or session metadata beyond the `user_id` FK.
- No changes to the `/ws` handshake protocol (still sends `{"token": "..."}`).
- No rate-limiting on `/token` (deferred to a future evolution).
- No change to the admin router or `require_admin` dependency.
- No user-facing "sessions page" UI — that is a client concern.
- Adding user info to the JWT *payload itself* (keeps tokens small — info
  stays in the response body only).

## User-visible functionality

### `/token` response — before

```json
{
  "access_token": "eyJ...",
  "token_type": "bearer"
}
```

### `/token` response — after

```json
{
  "access_token": "eyJ...",
  "token_type": "bearer",
  "refresh_token": "abc123...",
  "user_id": 1,
  "name": "alice",
  "nickname": "Ali",
  "is_admin": false
}
```

Existing clients that only read `access_token` and `token_type` continue to
work unchanged — extra JSON fields are silently ignored by standard parsers.

### JWT payload — before

```json
{"user_id": 1}
```

### JWT payload — after

```json
{"user_id": 1, "exp": 1715003600, "iat": 1715000000, "sub": "1"}
```

### New endpoints (additive, no breaking changes)

| Endpoint | Method | Auth | Body | Response |
|----------|--------|------|------|----------|
| `/token/refresh` | POST | None | `{"refresh_token": "..."}` | `{"access_token", "refresh_token", "token_type", "user_id", "name", "nickname", "is_admin"}` |
| `/token/revoke` | POST | None | `{"refresh_token": "..."}` | `{"status": "revoked"}` |
| `/token/revoke-all` | POST | Bearer | — | `{"revoked_count": N}` |

## Technical approach

### Baseline flow (current)

```
POST /token (username + password)
  → validate password (bcrypt)
  → jwt.encode(payload={"user_id": N}, key=MASTER_SECRET_KEY)
  → return {"access_token": "<jwt>", "token_type": "bearer"}
```

`decode_token`:
```
  → jwt.decode(token, key=MASTER_SECRET_KEY, algorithms=["HS256"], verify=True)
  → return int(decoded["user_id"])
```

No expiry, no refresh, no revocation, no user info, no standard claims.

### Proposed flow

**New schema** (`ppback/ppschema.py`):

```python
class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    refresh_token: str
    user_id: int
    name: str
    nickname: str
    is_admin: bool

class TokenRefreshIn(BaseModel):
    refresh_token: str

class TokenRefreshOut(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    user_id: int
    name: str
    nickname: str
    is_admin: bool

class TokenRevokeIn(BaseModel):
    refresh_token: str

class TokenRevokeAllOut(BaseModel):
    revoked_count: int
```

**Modified `/token` handler**:

```python
import time
import secrets
import hashlib

@router.post("/token", response_model=TokenResponse)
async def login(form_data: OAuth2PasswordRequestForm = Depends(), db: ...):
    # ... existing password validation ...
    now = int(time.time())
    token = jwt.encode(
        payload={"user_id": user.id, "exp": now + 3600, "iat": now, "sub": str(user.id)},
        key=MASTER_SECRET_KEY,
    )
    refresh_raw = secrets.token_urlsafe(32)
    token_hash = hashlib.sha256(refresh_raw.encode()).hexdigest()
    # INSERT refresh_token(user_id=user.id, token_hash=..., expires_at=now+30d)
    return TokenResponse(
        access_token=token,
        token_type="bearer",
        refresh_token=refresh_raw,
        user_id=user.id,
        name=user.name,
        nickname=user.nickname,
        is_admin=user.is_admin,
    )
```

**Token management flows**:

```
POST /token/refresh {"refresh_token": "<raw>"}
  → lookup by sha256(raw) where revoked=False AND expires_at > now
  → mark found row as revoked=True
  → issue new access_token (with exp, iat, sub) + new refresh_token (same user)
  → return TokenRefreshOut (includes user info)

POST /token/revoke {"refresh_token": "<raw>"}
  → lookup by sha256(raw)
  → set revoked=True
  → return {"status": "revoked"}

POST /token/revoke-all (Bearer <access_token>)
  → UPDATE refresh_tokens SET revoked=True WHERE user_id=decoded.sub AND revoked=False
  → return {"revoked_count": N}
```

**Updated `decode_token`** (`ppback/deps.py`):

```python
async def decode_token(token: Annotated[str, Depends(oauth2_scheme)]) -> int:
    decoded = jwt.decode(
        token,
        key=MASTER_SECRET_KEY,
        algorithms=["HS256"],
        verify=True,
        # options={"require": ["exp", "iat", "sub"]} — deferred to migration window
    )
    # Migration-warning for tokens lacking standard claims
    if "iat" not in decoded:
        logger.warning("Token without iat claim — upgrade client")
    if "sub" not in decoded:
        logger.warning("Token without sub claim — upgrade client")
    # exp is validated by PyJWT by default (verify=True checks exp if present)
    # but not required yet — see phase 3
    user_id = int(decoded["user_id"])
    return user_id
```

### Phases

1. **Phase 1 — Core** (~180 lines across 6 files):
   - New `RefreshToken` model in `ppdb_schemas.py`, Alembic migration.
   - DB helpers: `create_tokens`, `refresh_access_token`, `revoke_refresh_token`,
     `revoke_all_for_user` in `dbfuncs.py`.
   - `TokenResponse` + request/response schemas in `ppschema.py`.
   - Modify `/token` to include `exp`, `iat`, `sub` in JWT + user info and
     `refresh_token` in response.
   - New endpoints in `routers/users.py` (or new `routers/auth.py` — see phase 2).
   - Warning logs in `decode_token` for missing `iat`/`sub` (no hard reject yet).
   - **Deployed together**: refresh tokens and user-info-in-response ship at
     the same time because they touch the same `/token` handler and compose
     cleanly in `TokenResponse`.

2. **Phase 2 — Router extraction (optional)**:
   - Create `ppback/routers/auth.py`, move `/token` and all `/token/*` handlers
     there, register new router, remove `/token` from `users.py`.
   - URL paths do **not** change — clients are completely unaffected.

3. **Phase 3 — Migration window close** (deferred, ~2 releases):
   - Flip `decode_token` to `options={"require": ["exp", "iat", "sub"]}`.
   - Old tokens without these claims are rejected with 401.
   - Publish a release note.

### Alternatives considered

- **OPAQUE / PASETO instead of JWT**: unnecessary because JWT + refresh tokens
  are standard OAuth2 and all clients already speak `Authorization: Bearer`.
- **Server-side session store (Redis)**: adds operational complexity not
  justified for this project's scale. Refresh tokens in the application DB
  are sufficient.
- **Hard switch to require exp/iat/sub immediately**: would break every
  existing client token — unacceptable. A migration window is required.
- **Embed user info in the JWT payload itself**: rejected — increases token
  size (every request header), embeds mutable data (nickname changes would
  require re-login), and violates JWT slimness principle.
- **Separate `/me` endpoint instead**: just formalizes the extra round-trip
  we are eliminating. Adding fields to `/token` is more efficient.

### Affected modules

| Module | Change |
|--------|--------|
| `ppback/db/ppdb_schemas.py` | Add `RefreshToken` model |
| `ppback/db/dbfuncs.py` | Add `create_tokens`, `refresh_access_token`, `revoke_refresh_token`, `revoke_all_for_user` |
| `ppback/ppschema.py` | Add `TokenResponse`, `TokenRefreshIn`, `TokenRefreshOut`, `TokenRevokeIn`, `TokenRevokeAllOut` |
| `ppback/routers/users.py` | Modify `/token` handler: add `exp`/`iat`/`sub` to JWT, return user info + `refresh_token`; add `/token/refresh`, `/token/revoke`, `/token/revoke-all` (or moved — see below) |
| `ppback/routers/auth.py` **new** (phase 2) | Host all `/token*` endpoints |
| `ppback/main.py` | Register `auth.router` (phase 2) |
| `ppback/deps.py` | Add migration-warning logs for missing `iat`/`sub`; defer `require` option |
| `alembic/versions/` | New migration for `refresh_tokens` table |
| `ppback/init_db.py` | No change needed (new table has no seed data) |
| `tests/conftest.py` | No structural change (existing `/token` calls auto-include new fields) |

## Auth and websocket compatibility

- **`/token` response**: New fields `refresh_token`, `user_id`, `name`,
  `nickname`, `is_admin`. Standard JSON parsers ignore unknown fields — zero
  breakage. Clients that use `response["access_token"]` continue to work.
- **JWT payload**: New `exp`, `iat`, `sub` claims are **additive**.
  `decode_token` currently only reads `user_id` and ignores unknown claims.
  PyJWT's default `verify=True` checks `exp` if present (but does not require
  it). Old tokens (without these claims) continue to be accepted with a
  warning log during the migration window.
- **`/ws` handshake**: Unchanged — first message is still `{"token": "<jwt>"}`.
  The WS handler calls `decode_token` which returns `int(user_id)` — same
  contract as today. The handshake does not use `iat`, `sub`, or `exp`.
- **`OAuth2PasswordBearer`**: No change. The `tokenUrl="token"` parameter is
  a documentation hint, not a routing constraint — the URL `/token` does not
  change even if the handler moves to `auth.py`.
- **Token schema compatibility**: A token minted after this change is
  byte-identical in structure to the old one except for additional claims.
  Old and new tokens interoperate fully.

## Usability and documentation

- **Client benefit**: Mobile/web clients get `name`, `nickname`, and `is_admin`
  directly from the `/token` response, eliminating one API call on every login /
  app start. For admin-gated UIs, the `is_admin` field enables immediate UI
  routing without a follow-up request.
- **Refresh tokens**: Enable "remember me" sessions and logout without
  invalidating every token globally.
- **Error messages**:
  - `POST /token` with bad credentials: `400 "Incorrect username or password."`
    (unchanged).
  - Expired access token: `401` from FastAPI's `OAuth2PasswordBearer`
    (auto-handled).
  - `/token/refresh` with invalid/expired/revoked refresh token:
    `401 "Invalid or expired refresh token."`.
- **Docs to update**: `README.md` — update `/token` response example, add new
  endpoints to API summary. If router extraction happens: update API reference.

## Testability

### Unit / integration tests to add

| Test file | Tests |
|-----------|-------|
| `tests/test_api_users.py` | `/token` returns `refresh_token`, `user_id`, `name`, `nickname`, `is_admin` |
| `tests/test_api_users.py` | `/token` response fields match the DB record for each test user |
| `tests/test_api_users.py` | Admin user gets `is_admin: true` in `/token` response |
| `tests/test_api_users.py` | `/token/refresh` with valid token returns new pair + user info and old token is revoked |
| `tests/test_api_users.py` | `/token/refresh` with revoked/expired token returns 401 |
| `tests/test_api_users.py` | `/token/revoke` marks token revoked, subsequent refresh 401s |
| `tests/test_api_users.py` | `/token/revoke-all` revokes all tokens for user |
| `tests/test_api_users.py` | Access token with `exp`/`iat`/`sub` works for all existing endpoints |
| `tests/test_api_users.py` | Access token past `exp` returns 401 |
| `tests/test_api_users.py` | Old-style token (no `exp`/`iat`/`sub`) still passes `decode_token` during migration |
| `tests/test_api_users.py` | `/ws` handshake works with new token (if WS test infra exists) |

### Fixture changes (`tests/conftest.py`)

No structural fixture change required. The `client` fixture already calls
`/token` for each user — the response will automatically include the new
fields on upgrade. Tests that need user info can reference them directly
from the login response rather than querying the DB (an improvement).

### Manual smoke check

```bash
# boot the server
uvicorn ppback.main:app --lifespan=on

# login — check all new fields are present
curl -s -X POST http://localhost:8000/token \
  -d "username=alice&password=alice" \
  | python3 -m json.tool
# Expected: access_token, token_type, refresh_token, user_id, name, nickname, is_admin

# decode the token to verify exp, iat, sub
curl -s -X POST http://localhost:8000/token \
  -d "username=alice&password=alice" \
  | python3 -c "import sys,json,jwt; print(jwt.decode(json.load(sys.stdin)['access_token'], options={'verify_signature': False}))"
# Expected: {"user_id": 1, "exp": 1715..., "iat": 1715..., "sub": "1"}

# refresh — should get a new pair
# revoke — subsequent refresh should 401
```

## Complexity and rollout

- **Scope**: S (small) — ~180 lines of new code across 6-8 files, one new DB
  table, one new migration. Phase 2 (router extraction) adds ~50 lines moved.
- **Risk hotspots**:
  - **Race on rotation**: If two concurrent `/token/refresh` calls use the
    same refresh token, the second will find the first already marked revoked
    and return 401. This is correct behavior and consistent with OAuth2
    best practices (refresh token rotation detects theft).
  - **Token collision**: `secrets.token_urlsafe(32)` produces 192 bits of
    entropy — collision probability is negligible.
  - **Warning log spam**: If many clients use old tokens without `iat`/`sub`,
    the warning log in `decode_token` could be noisy. Mitigation: log at
    `warning` level once; after the migration window, switch to `require`.
- **Rollback**: Revert the code change, drop the `refresh_tokens` table via
  Alembic downgrade. Clients lose the ability to refresh but existing access
  tokens continue to work until they expire naturally (max 1 hour). Tokens
  minted with `iat`/`sub` during the change window continue to work (extra
  claims are harmless).

## A priori performance analysis

- **`/token`**: One additional DB insert per login. Adding `iat`/`sub`/`exp`
  to the JWT payload is CPU-cost-free (three dict entries). Fetching user info
  fields from the already-loaded `user_info` object adds zero DB queries.
  Response payload grows by ~100 bytes.
- **`/token/refresh`**: 2 DB queries (select + update insert). Called
  infrequently (every ~55 min per client). Also returns user info (same
  zero-DB-cost).
- **`/token/revoke`**: 1 DB update. Rare.
- **`/token/revoke-all`**: 1 bulk DB update. Extremely rare.
- **`decode_token`**: Negligible increase — two `if "iat" not in decoded`-style
  checks. No DB impact.
- **No impact on hot paths**: `/users`, `/conv`, `/usermsg`, `/ws` are
  completely unchanged.
- **Cache layer**: no cached functions are touched.
- **Hypothesis**: Total performance impact is negligible (< 0.1 ms per
  `/token` call). Validate post-implementation by comparing `timeout 5` boot
  test before and after.

## Risks and open questions

1. **Refresh token lifetime**: 30 days is the starting proposal. Should it be
   configurable via env var (`REFRESH_TOKEN_EXPIRY_DAYS`)? **Yes — add env var
   with a default of 30.**
2. **Migration window**: How long before we flip `require=["exp", "iat", "sub"]`?
   Suggestion: two releases (e.g. 2 months) with a warning log when a legacy
   token is used. Coordinate the hard-switch across all three claims at once.
3. **Should `/token/refresh` include user info fields?** Yes, for consistency —
   a client that refreshes should not lose access to user info. The schema
   (`TokenRefreshOut`) includes them.
4. **Should `sub` be integer or string?** String per JWT spec (RFC 7519 §4.1.2).
   The existing `user_id` numeric claim is preserved for backward compatibility.
5. **Is auth router extraction worth the churn?** The benefits are separation
   of concerns and a natural home for future auth endpoints. If implemented
   alongside the new refresh/revoke endpoints, the extraction pays for itself.
6. **Test speed**: The monolithic `client` fixture rebuilds the DB per test.
   Adding ~12 tests multiplies runtime proportionally. Acceptable for now
   (adds ~4s) but worth optimizing in a separate evolution.

## Decision record

- **Status**: draft
- **Resolution**: —
- **Note**: This document supersedes `evol-jwt-refresh.md` and
  `evol-jwt-security.md`, merging both into a single coherent evolution.

## References

- `ppback/routers/users.py:37-69` — current `/token` implementation
- `ppback/deps.py:33-41` — current `decode_token` implementation
- `ppback/ppschema.py` — existing schemas (add `TokenResponse` etc.)
- `ppback/config.py:14` — `MASTER_SECRET_KEY` env var
- `ppback/main.py:73-76` — router registration
