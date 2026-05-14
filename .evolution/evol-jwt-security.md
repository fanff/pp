---
id: evol-jwt-security
status: draft
created: 2026-05-14
authors: [opencode]
related:
  - evol-jwt-refresh.md  # covers exp, refresh tokens, revocation
supersedes: []
superseded-by: ""
---

## Summary

Enhance the `/token` endpoint response to include basic user profile fields
(user_id, name, nickname, is_admin), add standard JWT claims (`iat`, `sub`),
and optionally migrate the auth endpoint to a dedicated `auth.py` router —
reducing client round-trips and improving JWT conformance without breaking
existing clients.

This document is scoped to **complement** `evol-jwt-refresh.md`, which covers
JWT expiration (`exp`), refresh tokens, and revocation. The two evolutions can
be implemented independently or as a combined release.

## Motivation and context

- **Current behavior**: `POST /token` at `ppback/routers/users.py:65-69` returns
  only `{"access_token": "<jwt>", "token_type": "bearer"}`. The JWT payload
  contains only `{"user_id": N}` — no `iat`, `sub`, or `exp`.

- **Problem**:
  1. **Extra round-trip**: Every client that needs the current user's name,
     nickname, or admin status must issue a separate API call (e.g.
     `GET /users` or an admin check). This is wasteful for the common case:
     the client already has the user's credentials at login time.
  2. **No standard claims**: The JWT lacks `iat` (issued-at) and `sub`
     (subject), making audit, debugging, and token introspection harder than
     necessary. Missing `iat` also means there is no anchor point for
     determining token age.
  3. **Auth living in `users.py`**: The `/token` endpoint is mixed into the
     users router alongside friend requests and invite codes — a separation-of-
     concerns smell. Auth is a cross-cutting concern, not a user feature.

- **Why now**: Low-risk additive change. The missing `iat`/`sub` fields are
  free to add (no DB impact). Including user info in the token response is a
  simple schema change with measurable client-side benefit (saves one HTTP
  round-trip per login / page load). Router extraction can wait for a follow-up
  if scope needs trimming.

- **Constraints**:
  - Must not break clients that parse `response["access_token"]` and ignore
    extra fields (standard JSON client behavior).
  - `decode_token` must continue to return `int(user_id)` — no schema change
    to the return type.
  - `/ws` handshake (first message `{"token": "<jwt>"}`) is unaffected; it
    relies only on `decode_token(user_id)`.
  - JWT expiration (`exp`) is handled by the sibling `evol-jwt-refresh.md`;
    this doc does not re-specify it, but the changes are compatible.

## Goals

1. `/token` response includes `user_id`, `name`, `nickname`, `is_admin` alongside
   `access_token` and `token_type`.
2. JWT payload gains `iat` (UTC epoch seconds at issuance) and `sub` (user_id as
   string, matching standard JWT semantics).
3. (Optional) Move `/token` from `routers/users.py` to a new `routers/auth.py`,
   registered in `main.py` as a separate router.
4. (Optional) `/token/refresh` endpoint — covered fully by `evol-jwt-refresh.md`;
   this doc only notes the integration point.
5. Zero backward-compatibility breakage for HTTP clients and WS handshake.
6. `decode_token` continues to accept tokens without `iat`/`sub` during a
   migration window (default: accept missing, log warning).

## Non-goals

- JWT expiration (`exp`) and refresh token mechanism — see `evol-jwt-refresh.md`.
- Token revocation, device management, or session listing.
- Rate-limiting on `/token`.
- Changes to the `/ws` handshake protocol or socket manager.
- Changes to admin router or `require_admin` dependency.
- Adding user info to the JWT *payload itself* (it stays in the response body
  only, keeping the token size small).

## User-visible functionality

### Additive changes — no breaking changes

**Before** (`POST /token`):
```json
{
  "access_token": "eyJ...",
  "token_type": "bearer"
}
```

**After** (`POST /token`):
```json
{
  "access_token": "eyJ...",
  "token_type": "bearer",
  "user_id": 1,
  "name": "alice",
  "nickname": "Ali",
  "is_admin": false
}
```

Existing clients that only read `access_token` and `token_type` continue to
work unchanged — extra JSON fields are silently ignored by standard parsers.

**JWT payload before**:
```json
{"user_id": 1}
```

**JWT payload after**:
```json
{"user_id": 1, "iat": 1715000000, "sub": "1"}
```

The `iat` and `sub` claims are validated by `decode_token` only in a
**lenient** mode initially: missing `iat`/`sub` is logged as a warning but
does not reject the token. A hard requirement can be activated after a
migration window (e.g. 2 releases), coordinated with `evol-jwt-refresh.md`'s
`exp` enforcement.

### Optional: router extraction

If `/token` moves to `routers/auth.py`:

| Endpoint | Old location | New location |
|----------|-------------|--------------|
| `POST /token` | `routers/users.py` | `routers/auth.py` |
| `POST /token/refresh` (from `evol-jwt-refresh.md`) | N/A | `routers/auth.py` |
| `POST /token/revoke` (from `evol-jwt-refresh.md`) | N/A | `routers/auth.py` |

The URL path `/token` does **not** change — only the internal handler moves.
Clients are completely unaffected.

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

### Proposed change

**Step 1 — New schema** (`ppback/ppschema.py`):

```python
class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user_id: int
    name: str
    nickname: str
    is_admin: bool
```

**Step 2 — Modified `/token` handler** (in `ppback/routers/users.py` or new
`routers/auth.py`):

```python
import time

@router.post("/token", response_model=TokenResponse)
async def login(...):
    # ... existing password validation ...
    now = int(time.time())
    token = jwt.encode(
        payload={"user_id": user_info.id, "iat": now, "sub": str(user_info.id)},
        key=MASTER_SECRET_KEY,
    )
    return TokenResponse(
        access_token=token,
        token_type="bearer",
        user_id=user_info.id,
        name=user_info.name,
        nickname=user_info.nickname,
        is_admin=user_info.is_admin,
    )
```

**Step 3 — Updated `decode_token`** (`ppback/deps.py`):

```python
async def decode_token(token: Annotated[str, Depends(oauth2_scheme)]) -> int:
    decoded = jwt.decode(
        token,
        key=MASTER_SECRET_KEY,
        algorithms=["HS256"],
        verify=True,
        # options={"require": ["iat", "sub"]} — deferred to migration window
    )
    # Migration-warning for tokens lacking iat/sub
    if "iat" not in decoded:
        logger.warning("Token without iat claim — upgrade client")
    if "sub" not in decoded:
        logger.warning("Token without sub claim — upgrade client")
    user_id = int(decoded["user_id"])
    return user_id
```

**Step 4 (optional) — New router `ppback/routers/auth.py`**:

```python
from fastapi import APIRouter, Depends, HTTPException
# ... move /token handler here, add /token/refresh if implementing

router = APIRouter()
```

Registered in `ppback/main.py`:
```python
from ppback.routers import auth  # new
app.include_router(auth.router)
```

The `users.py` router would lose the `/token` handler and the `jwt` import.
Existing imports of `decode_token`, `get_db`, `check_password` remain.

### Phases

1. **Phase 1 — Core schema + payload**: Add `iat`/`sub` to JWT, add
   `TokenResponse` schema, modify `/token` handler to return user info.
   `decode_token` accepts old tokens with a warning log. **No router move.**
   *(Estimated: ~30 lines changed across 3 files, no migration, no DB change.)*

2. **Phase 2 — Router extraction (optional)**: Create `routers/auth.py`, move
   `/token` handler, register new router, remove `/token` from `users.py`.
   Coordinate with `evol-jwt-refresh.md` if also implementing refresh endpoints.
   *(Estimated: ~50 lines moved, no behavior change.)*

3. **Phase 3 — Migration window close** (coordinated with `evol-jwt-refresh.md`):
   Flip `decode_token` to `require=["iat", "sub"]` (and `require=["exp"]` from
   sibling doc). Publish a release note. *(Deferred to a future release.)*

### Alternatives considered

- **Embed user info in the JWT payload itself**: Rejected — it increases token
  size (affects every request header), embeds mutable data (nickname changes
  would require re-login), and violates the principle of keeping JWTs slim.
  User info belongs in the response body.
- **Separate `/me` endpoint instead**: Already considered, but that just
  formalizes the extra round-trip we are trying to eliminate. Adding fields to
  `/token` is more efficient.
- **`sub` as integer instead of string**: JWT spec (RFC 7519 §4.1.2) defines
  `sub` as a StringOrURI. Using `str(user_id)` is spec-compliant; the existing
  `user_id` numeric claim remains for backward compatibility.
- **Skip `iat` entirely**: Possible, but `iat` is a zero-cost addition that
  enables future token-age-based policies (e.g. "force re-login after 30 days").

### Affected modules

| Module | Change |
|--------|--------|
| `ppback/ppschema.py` | Add `TokenResponse` model |
| `ppback/routers/users.py` | Modify `/token` handler: add `iat`/`sub` to payload, return user info |
| `ppback/deps.py` | Add migration-warning logs for missing `iat`/`sub`; defer `require` option |
| `ppback/routers/auth.py` **new** (phase 2) | Host `/token` and future auth endpoints |
| `ppback/main.py` | Register `auth.router` (phase 2) |
| `ppback/config.py` | No change needed (`MASTER_SECRET_KEY` env var unchanged) |
| `ppback/db/ppdb_schemas.py` | No change |
| `ppback/db/dbfuncs.py` | No change |
| `alembic/versions/` | No change |
| `ppback/init_db.py` | No change |
| `tests/conftest.py` | May need minor update (see Testability) |

## Auth and websocket compatibility

- **`/token` response**: New fields `user_id`, `name`, `nickname`, `is_admin`.
  Standard JSON parsers ignore unknown fields — zero breakage.
- **JWT payload**: New `iat` and `sub` claims are **additive**. `decode_token`
  currently only reads `user_id` and ignores unknown claims. Old tokens (no
  `iat`, no `sub`) continue to be accepted with a warning log.
- **`/ws` handshake**: Unchanged — first message is still `{"token": "<jwt>"}`.
  The WS handler calls `decode_token` which returns `int(user_id)` — same
  contract as today.
- **`OAuth2PasswordBearer`**: No change. The `tokenUrl="token"` parameter is
  a documentation hint, not a routing constraint — the URL `/token` does not
  change even if the handler moves to `auth.py`.
- **Token schema compatibility**: A token minted after this change is
  byte-identical in structure to the old one except for additional claims.
  PyJWT's default `verify=True` ignores claims it does not understand. Old
  and new tokens interoperate fully.

## Usability and documentation

- **Client benefit**: Mobile/web clients can extract `name`, `nickname`, and
  `is_admin` directly from the `/token` response, eliminating one API call on
  every login / app start. For admin-gated UIs, the `is_admin` field enables
  immediate UI routing without a follow-up request.
- **Error messages**: Unchanged — `/token` still returns
  `400 "Incorrect username or password."` for bad credentials. Token auth
  failures return `401` (auto-handled by `OAuth2PasswordBearer`).
- **Docs to update**:
  - `README.md` — update the `/token` response example to include new fields.
  - If router extraction happens: update API documentation to mention the
    `auth` router.
  - No CHANGELOG update until release.

## Testability

### Unit / integration tests to add

| Test file | Tests |
|-----------|-------|
| `tests/test_api_users.py` | `POST /token` returns `user_id`, `name`, `nickname`, `is_admin` fields |
| `tests/test_api_users.py` | `POST /token` response fields match the DB record for each test user |
| `tests/test_api_users.py` | Old-style token (decoded, no `iat`/`sub`) still passes `decode_token` |
| `tests/test_api_users.py` | Token with `iat`/`sub` passes `decode_token` and returns correct `user_id` |
| `tests/test_api_users.py` | `/ws` handshake works with new token (if WS test infra exists) |
| `tests/test_api_users.py` | Admin user gets `is_admin: true` in `/token` response |

### Fixture changes (`tests/conftest.py`)

The `client` fixture already calls `/token` for each seeded user and captures
the token. After this change, the response will include user info fields.
Tests that need user info can reference them directly from the login response
rather than querying the DB — an improvement.

No structural fixture change is required; the existing token extraction logic
(`response.json()["access_token"]`) continues to work.

### Manual smoke check

```bash
# boot
uvicorn ppback.main:app --lifespan=on

# login — check user info fields are present
curl -s -X POST http://localhost:8000/token \
  -d "username=alice&password=alice" \
  | python3 -m json.tool
# Expected: access_token, token_type, user_id, name, nickname, is_admin

# decode the token to verify iat and sub
curl -s -X POST http://localhost:8000/token \
  -d "username=alice&password=alice" \
  | python3 -c "import sys,json,jwt; print(jwt.decode(json.load(sys.stdin)['access_token'], options={'verify_signature': False}))"
# Expected: {"user_id": 1, "iat": 1715..., "sub": "1"}
```

### Backward-compatibility regression check

```bash
# Manually craft a token without iat/sub (simulating old client)
python3 -c "
import jwt, time
token = jwt.encode({'user_id': 1}, key='mydummykey')
print(token)
" | xargs -I{} curl -s -H "Authorization: Bearer {}" http://localhost:8000/users
# Expected: 200 (not 401), with a warning log line about missing iat/sub
```

## Complexity and rollout

- **Scope**: XS–S (very small for Phase 1, ~30 lines across 3 files, zero DB
  changes). Phase 2 (router extraction) is S (~50 lines moved).
- **Risk hotspots**:
  - **None significant**: The change is additive. The only runtime-path code
    change is adding `iat` and `sub` to `jwt.encode()` and adding fields to the
    response dict. Both are trivially verifiable.
  - **Warning log spam**: If many clients use old tokens without `iat`/`sub`,
    the warning log in `decode_token` could be noisy. Mitigation: log at
    `warning` level once; after the migration window, switch to `require`.
- **Rollback**: Revert the code change. Tokens minted with `iat`/`sub` during
  the change window will continue to work (extra claims are harmless). The
  only side-effect is clients that started depending on the new response fields
  will lose them — an additive-contract rollback that is safe for tolerant
  clients.
- **Dependency on `evol-jwt-refresh.md`**: None for Phase 1. The two
  evolutions can be implemented and deployed independently. If both are
  deployed together, the combined `/token` response would include `user_info`
  fields (from this doc) and `refresh_token` (from the sibling doc) — they
  compose cleanly.

## A priori performance analysis

- **`/token` latency**: Negligible increase. Adding `iat` and `sub` to the JWT
  payload is a CPU-cost-free operation (two dict entries). Fetching `name`,
  `nickname`, `is_admin` from the already-loaded `user_info` object adds zero
  DB queries. The response payload grows by ~50 bytes.
- **`decode_token` latency**: Negligible increase — one `if "iat" not in
  decoded` check. No DB impact.
- **Hot paths**: `/users`, `/conv`, `/usermsg`, `/ws` are completely unchanged.
- **Cache layer**: No cached functions are touched.
- **Hypothesis**: Total performance impact is < 0.01 ms per `/token` call.
  Validate post-implementation by running the `timeout 5` boot strace and
  comparing latency percentiles from Jaeger traces (if tracing is enabled).

## Risks and open questions

1. **Should `iat` and `sub` be required immediately?** No — existing tokens
   lack them. A migration window (2 releases) with a warning log is the safer
   approach. Coordinate the hard-switch with `evol-jwt-refresh.md`'s `exp`
   requirement.
2. **Should user info fields be included in `/token` if refresh tokens are
   also present?** Yes — the response shapes compose: `TokenResponse` from
   this doc and `TokenRefreshResponse` from the sibling doc both extend the
   base fields. The combined response would include all fields.
3. **Should we also return user info from `/token/refresh`?** Yes, for
   consistency — a client that refreshes its token should not lose access to
   user info. The sibling doc should be updated to include the same user info
   fields in its refresh response. This is a low-cost addition to that doc's
   schema.
4. **Should `sub` be the user_id integer or string?** String per JWT spec
   (RFC 7519 §4.1.2). The existing `user_id` numeric claim is preserved for
   backward compatibility — `decode_token` reads `user_id`, not `sub`, so the
   return type contract is unchanged.
5. **Is the auth router extraction worth the churn?** The benefits are
   separation of concerns and a natural home for future auth endpoints
   (`/token/refresh`, `/token/revoke`). If the sibling doc is also implemented,
   the extraction pays for itself immediately. If only Phase 1 of this doc is
   implemented, the extraction can be deferred.

## Decision record

- **Status**: draft
- **Resolution**: —

## References

- `ppback/routers/users.py:37-69` — current `/token` implementation
- `ppback/deps.py:33-41` — current `decode_token` implementation
- `ppback/ppschema.py` — existing schemas (add `TokenResponse`)
- `ppback/config.py:14` — `MASTER_SECRET_KEY` env var
- `ppback/main.py:73-76` — router registration
- `.evolution/evol-jwt-refresh.md` — sibling evolution covering `exp`, refresh
  tokens, and revocation (compatible with this doc)
