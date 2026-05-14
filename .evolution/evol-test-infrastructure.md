---
id: evol-test-infrastructure
status: draft
created: 2026-05-14
authors: [opencode]
related: []
supersedes: []
superseded-by: ""
---

## Summary

Overhaul the PP Network test infrastructure to eliminate anti-patterns, remove
fragile hardcoded assumptions, and close critical coverage gaps. The synchronous
`@pytest.fixture` that wraps `asyncio.run()` is converted to a native async
fixture. Hardcoded user IDs (e.g. `user_id == 3`) are replaced with data-driven
lookups. New test suites cover conversation member management, invite code edge
cases, WebSocket multi-client scenarios, concurrent writes, and proper cache
hit/miss verification.

## Motivation and context

- **Current behavior**: The `client` fixture in `tests/conftest.py:25-121` is a
  synchronous `@pytest.fixture()` that calls `asyncio.run(setup_db())` and
  `asyncio.run(teardown_db())`. This works but pollutes the event loop, makes
  test isolation harder, and prevents mixing async and sync fixtures cleanly.

- **Hardcoded user IDs**: Tests like `test_api_users.py:35` assert
  `fr_resp.json()["to_user_id"] == 3` (charlie), and
  `test_api_users.py:42` asserts `accept_resp.json()["user_id"] == 1` (alice).
  `test_api_convs.py:34` asserts `sorted(data["members"]) == [1, 2]`.
  `test_api_admin.py:37` uses `# bob is user_id=2` as a comment-coded invariant.
  If the seed order changes (e.g. diana is added as first user), every numeric
  ID assertion breaks.

- **Coverage gaps**:
  - No tests for adding/removing conversation members or changing roles via
    standard (non-admin) endpoints — only admin role changes are tested.
  - No invite code edge cases: expired codes, invalid codes, reusing the same
    code, submitting a code for yourself.
  - No concurrent access tests: two users writing to the same conversation
    simultaneously, or racing on friend requests.
  - Only one WebSocket test (`test_api_messages_ws.py:1-25`) that tests a single
    client. No reconnection, no multi-client, no WS token expiry handling.
  - `test_cache_types.py` calls each cached function twice but never asserts
    cache hit vs cache miss — it only checks that the return type is correct.

- **Why now**: The test suite is the safety net for all future evolution. Before
  adding significant new features (JWT refresh, member management endpoints,
  real-time features), the test foundation must be reliable, maintainable, and
  comprehensive. Tightening the fixture and removing fragility lowers the cost
  of every subsequent change.

- **Constraints**:
  - The `client` fixture is used by every test — any refactor must keep its
    external contract (yields `(TestClient, tuple_of_4_tokens)`).
  - Tests must remain fast enough for regular `pytest` runs (< 10s total).
  - Must not introduce external dependencies (no Redis, no Docker compose).
  - Must stay compatible with the current `pytest.ini` (no `asyncio_mode=auto`
    yet — currently tests use `@pytest.mark.asyncio` per-test).

## Goals

1. **Async-native fixture**: Convert `client` to `@pytest_asyncio.fixture`
   (or equivalent) so `asyncio.run()` is eliminated. The fixture body uses
   `async with` throughout.

2. **Named user/token lookup**: Replace `(alice_token, bob_token, ...)` tuple
   unpacking with a dict or namedtuple so tests write
   `client, users = fixture` and access `users.alice.token`,
   `users.alice.id`, etc.

3. **Member management tests**: Cover adding members, removing members, and
   role changes via standard endpoints (not just admin).

4. **Invite code edge case tests**: Invalid code, expired code, self-invite,
   duplicate submission, code reuse after acceptance.

5. **Concurrent access tests**: At least one test exercising two users sending
   messages simultaneously to the same conversation, verifying both messages
   are persisted and ordered correctly.

6. **WebSocket multi-client and reconnection tests**: Two WS clients connected
   simultaneously; disconnect/reconnect cycle; verify events are delivered to
   the correct clients.

7. **Cache hit/miss verification**: `test_cache_types.py` is updated to
   prove that the second call returns cached data (e.g. by mocking time or
   checking that the underlying DB query is not executed).

8. **All existing tests continue to pass** — no regressions.

## Non-goals

- No migration away from `TestClient` to `httpx.AsyncClient` (deferred — would
  require rewriting every test).
- No parallel test execution (`pytest -n auto`) — the `client` fixture mutates
  global FastAPI state (cache) and is not re-entrant.
- No changes to `pytest.ini` aside from adding `asyncio_mode = auto` if
  consensus favors it (discussed in Risks).
- No new CI pipeline or coverage reporting infrastructure.
- No load/stress tests beyond the concurrent access scenario.

## User-visible functionality

No user-visible changes. This evolution targets only the test suite and fixture
infrastructure. The API, schema, auth flow, and WebSocket protocol are
unchanged.

## Technical approach

### Baseline (current test infrastructure)

```
tests/conftest.py:25-121
  @pytest.fixture()                 ← synchronous
    asyncio.run(setup_db())          ← blocks event loop
    FastAPICache.init(...)           ← global state mutation
    TestClient(app)                  ← synchronous FastAPI test client
    client.post("/token") x4        ← gets tokens
    yield client, (a,b,c,d)         ← yields tuple of tokens
    asyncio.run(teardown_db())

tests/test_api_users.py:5
  client, (alice_token, ...) = client   ← fragile tuple unpacking
  assert fr_resp.json()["to_user_id"] == 3   ← hardcoded user ID
```

### Proposed change

**1. Convert fixture to native async**

Replace `@pytest.fixture()` with `@pytest_asyncio.fixture` (from
`pytest-asyncio`). The fixture body becomes fully async, removing
`asyncio.run()`:

```python
@pytest_asyncio.fixture
async def client():
    async with dbengine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)

    async with SessionLocal() as db:
        users = await add_users(db, [
            ["alice", "testpassword"],
            ["bob", "testpassword"],
            ["charlie", "testpassword"],
            ["diana", "testpassword"],
        ])
        users[3].is_admin = True
        await db.commit()
        for u in users:
            await db.refresh(u)
        # ... seed conversations, invites, friends

    # Tokens still obtained via synchronous TestClient.post()
    # because TestClient is synchronous. This is acceptable — the
    # DB setup is async, the token calls are fast HTTP operations.
```

**Key consideration**: `TestClient` is synchronous. The HTTP token calls must
remain synchronous. The pattern is: async DB setup → sync HTTP token fetch →
yield. This is a one-directional conversion that doesn't require
`httpx.AsyncClient`.

However, there is a known gotcha: `@pytest_asyncio.fixture` creates an async
generator. Mixing sync `TestClient` calls inside it is fine as long as no
nested event loops are created. The `TestClient` runs its own event loop in a
separate thread, so there is no conflict.

**2. Structured user/token lookup**

Replace the flat 4-tuple with a small dataclass or namedtuple:

```python
from dataclasses import dataclass

@dataclass
class TestUsers:
    alice: UserInfo
    bob: UserInfo
    charlie: UserInfo
    diana: UserInfo
    tokens: dict[str, str]  # username → token

# Fixture yields (TestClient, TestUsers)
```

Tests then write:

```python
async def test_friend_request_flow(client):
    rest_client, users = client
    ic_resp = rest_client.post(
        "/invite-codes",
        headers={"Authorization": f"Bearer {users.tokens['charlie']}"},
    )
    # ...
    assert fr_resp.json()["to_user_id"] == users.charlie.id
```

This eliminates all hardcoded numeric IDs and token tuple indexing.

**3. New test modules**

| Module | Content |
|--------|---------|
| `tests/test_api_members.py` | Member add/remove/role via non-admin endpoints (if they exist) or explicit 403/404 testing |
| `tests/test_invite_codes.py` | Invalid code, expired code, self-invite, reuse, duplicate submission |
| `tests/test_concurrent.py` | Two users write to same conversation concurrently; friend request race |
| `tests/test_ws_multi.py` | Two WS clients, disconnect/reconnect, event delivery verification |
| `tests/test_cache_types.py` | Update existing to verify cache hit vs miss (e.g. spy on DB queries) |

**4. Cache hit/miss verification**

`test_cache_types.py` currently calls `hook_user(db, 1)` twice and asserts type
correctness. To verify cache behavior, introduce a counter or mock on the
underlying DB query. Since the cache is in-memory (`InMemoryBackend`), a simple
approach: patch `SessionLocal` (or the query method) to count calls, then
assert the second call didn't hit the DB. Alternatively, use
`FastAPICache.get_backend().get(...)` introspection after the first call to
assert the key exists in cache.

### Phases

**Phase 1 — Fixture conversion + named lookups**
- Convert `conftest.py` to `@pytest_asyncio.fixture`
- Introduce `TestUsers` dataclass with user objects and token dict
- Update all 5 test files to use named lookups instead of tuple unpacking and
  hardcoded IDs
- Verify all existing tests pass

**Phase 2 — New coverage**
- Add `test_api_members.py` tests
- Add `test_invite_codes.py` tests
- Update `test_cache_types.py` with cache hit/miss assertions
- Verify all tests pass

**Phase 3 — Advanced scenarios**
- Add `test_concurrent.py` with async concurrency using `asyncio.gather`
- Add `test_ws_multi.py` with multi-client WebSocket scenarios
- Verify all tests pass

### Alternatives considered

- **Switch to `httpx.AsyncClient`**: Would allow fully async tests end-to-end
  but requires rewriting every test and fixture. Deferred to a separate
  evolution. Phase 1 explicitly keeps `TestClient` to minimize churn.

- **Use `pytest-asyncio` with `asyncio_mode = auto`**: Would remove the need
  for `@pytest.mark.asyncio` on every test. However, this could silently change
  behavior of tests that are not async-safe. Safer to add this after the
  fixture conversion and verify no regressions. Marked as an option in Risks.

- **Factory fixtures instead of monolithic `client`**: Breaking the monolithic
  fixture into smaller composable fixtures (e.g., `db_session`, `tokens`,
  `users`) would be cleaner but requires changing every test's fixture list.
  Deferred; the monolith is well-known and works.

- **Database transaction rollback instead of drop/create**: Faster isolation
  per test, but `TestClient` runs in a separate thread, making transaction
  sharing complex. Deferred.

### Affected modules

| Module | Change |
|--------|--------|
| `tests/conftest.py` | Convert to `@pytest_asyncio.fixture`, add `TestUsers` dataclass, seed user objects |
| `tests/test_api_users.py` | Use named lookups, remove hardcoded IDs |
| `tests/test_api_convs.py` | Use named lookups, remove hardcoded IDs |
| `tests/test_api_messages_ws.py` | Use named lookups, remove hardcoded IDs |
| `tests/test_api_admin.py` | Use named lookups, remove hardcoded IDs |
| `tests/test_cache_types.py` | Add cache hit/miss assertions |
| `tests/test_api_members.py` **new** | Member management tests |
| `tests/test_invite_codes.py` **new** | Invite code edge cases |
| `tests/test_concurrent.py` **new** | Concurrent access tests |
| `tests/test_ws_multi.py` **new** | WS multi-client/reconnection tests |
| `pyproject.toml` | Add `pytest-asyncio` (already present as `pytest-asyncio>=1.1.0` — verify version is sufficient) |

## Auth and websocket compatibility

- **No changes to `/token` flow or JWT payload**. Tests fetch tokens via the
  real `/token` endpoint (unchanged). The fixture conversion does not modify
  any `ppback/` code.
- **No changes to `/ws` handshake**. WebSocket tests use
  `TestClient.websocket_connect("/ws")` and send `{"token": "<jwt>"}` as the
  first message — identical to current behavior.
- **Backward compatibility**: Full. Only test infrastructure files are touched.

## Usability and documentation

- `AGENTS.md` — update the "Testing Details" section to reflect the new async
  fixture and structured user lookup pattern.
- `tests/README.md` (if it exists) — update; otherwise create a brief testing
  guide.
- Error messages: unchanged. No new user-facing errors are introduced.

## Testability

*(This section describes how the evolution itself will be validated.)*

- **Phase 1 validation**: Run `pytest -v` — all existing tests pass with
  identical assertions. No test logic changes, only fixture and lookup changes.
  Verify by diffing test output against baseline (`--tb=short`).
- **Phase 2 validation**: Run new tests in isolation (`pytest -v tests/test_api_members.py tests/test_invite_codes.py`)
  then full suite (`pytest`) — no regressions.
- **Phase 3 validation**: Run `pytest -v tests/test_concurrent.py tests/test_ws_multi.py`
  — these tests are inherently timing-sensitive; verify they pass consistently
  (3 consecutive runs).
- **Manual smoke check**: Boot the server with `uvicorn ppback.main:app --lifespan=on`
  and run basic curl commands to confirm the API itself is unaffected.

### Tests to add/update

| Test file | Tests |
|-----------|-------|
| `test_api_members.py` | Add member to conversation; remove member; change role via non-admin endpoint (if exists); non-member cannot add member; add non-existent user returns 404 |
| `test_invite_codes.py` | POST with invalid code returns 404/400; expired code returns 410/400; self-invite returns 400; reuse code after acceptance returns 400; duplicate submission returns 400 |
| `test_concurrent.py` | Two users send messages to same conversation concurrently via `asyncio.gather` — both succeed, messages are ordered by `id`; two users send friend request to same user concurrently — at most one succeeds |
| `test_ws_multi.py` | Two WS clients connect, both receive `message.created` event when a third user posts; WS client reconnects and receives missed event (or verifies no duplicate); WS client with invalid token is rejected |
| `test_cache_types.py` | After first `hook_user` call, verify cache key exists; patch DB query to count calls, assert second call does not invoke DB |

## Complexity and rollout

- **Scope**: M (medium) — ~400-500 lines across existing and new files. No
  production code changes.
- **Risk hotspots**:
  - **Async fixture + sync TestClient mix**: The `@pytest_asyncio.fixture`
    contains `TestClient.post()` calls (synchronous). This is known to work
    because `TestClient` runs FastAPI in a separate thread. However, if the
    fixture also uses `async with SessionLocal()` before the yield, the event
    loop state must be clean. Mitigation: test the fixture conversion first
    with a single test before updating all tests.
  - **Global cache state**: `FastAPICache.init()` and `.reset()` are called in
    the fixture. If `@pytest_asyncio.fixture` is scoped to `function` (default),
    each test gets a fresh cache, which is correct. Ensure the fixture
    explicitly resets cache both before and after (as it does now).
  - **Concurrent tests flakiness**: `asyncio.gather` inside a test is
    deterministic only if the server processes requests in publication order.
    Use a small delay or barrier pattern to ensure both writes are in-flight
    simultaneously. Accept minor flakiness and document.
- **Rollback**: Revert all changes to `tests/` and `pyproject.toml`. The test
  suite returns to its current state with zero impact on production or users.

## A priori performance analysis

- **Fixture overhead**: The async fixture is not measurably different from the
  current `asyncio.run()` approach. Both create/drop the same tables and seed
  the same data. No change in per-test runtime.
- **New tests**: Each test creates/fixture-isolates a fresh database. Adding
  ~20 new tests will increase total suite runtime proportionally (~3-5s).
  Acceptable for a ~10-15s total suite.
- **Concurrent tests**: `asyncio.gather` runs tasks concurrently within a single
  test — no additional wall-clock overhead beyond the slowest subtask.
- **WebSocket multi-client tests**: `TestClient.websocket_connect` opens a
  real WebSocket connection. Two concurrent WS connections double the server
  thread count momentarily but is negligible.
- **No impact on production hot paths**: zero changes to `ppback/` code.
- Hypothesis: total test suite runtime increases from ~5s to ~15s. Validate by
  running `time pytest` before and after.

## Risks and open questions

1. **`pytest-asyncio` version**: `pyproject.toml` pins `pytest-asyncio>=1.1.0`.
   The `@pytest_asyncio.fixture` decorator was added in v0.17 (it was named
   `@pytest.fixture` before that). Need to verify the installed version
   supports `@pytest_asyncio.fixture`. If not, bump to `>=1.1.0` is sufficient?
   Actually `pytest-asyncio` has `@pytest_asyncio.fixture` since early
   versions. Let's confirm: yes, `pytest_asyncio.fixture` exists since at least
   0.12. The `>=1.1.0` pin is fine.

2. **`asyncio_mode` setting**: Should we set `asyncio_mode = auto` in
   `pytest.ini` to avoid needing `@pytest.mark.asyncio` on every test? Risk:
   tests that are not async-aware would need to be explicitly marked with
   `@pytest.mark.no_asyncio`. **Decision deferred** — start with explicit marks
   (current pattern), add `asyncio_mode = auto` in a follow-up if desired.

3. **TestClient + async fixture event loop interactions**: `TestClient` runs
   the ASGI app in a separate thread with its own event loop. The
   `@pytest_asyncio.fixture` runs in the test's event loop. The two loops do
   not nest. However, if the fixture holds a DB session open across the yield,
   the `TestClient`'s requests (which may use `get_db`) will open separate
   sessions. No conflict expected.

4. **Concurrent test determinism**: How to guarantee two messages are sent
   "simultaneously" in a test? Use `asyncio.gather` without awaiting between
   the two `client.post()` calls. This submits both requests to the server
   thread pool nearly simultaneously. For friend-request races, use
   `asyncio.gather(*[submit_friend_request(user) for user in users])` and
   assert exactly one succeeds. Accept that on extremely slow CI, both may
   succeed (rare). Document as a known limitation.

5. **WS reconnection test**: Does `TestClient` support reconnecting the same
   `websocket_connect` context manager? Yes — close the first connection,
   open a new one. The test should verify that the new connection receives
   future events. Missed events are not replayed (current behavior), so the
   test should verify only future events, not history.

6. **Cache spy approach**: To verify cache hit vs miss, the simplest approach
   is to patch `SessionLocal.execute` with a counter before the second
   `hook_user` call. Alternative: use `FastAPICache.get_backend().get(key)`
   to check cache contents directly. Both are acceptable; prefer the counter
   approach because it proves the DB was not touched.

## Decision record

- **Status**: draft
- **Resolution**: —

## References

- `tests/conftest.py` — current fixture (lines 25-121)
- `tests/test_api_users.py` — hardcoded `user_id == 3` (line 35)
- `tests/test_api_admin.py` — comment-coded `user_id=2` (line 36)
- `tests/test_cache_types.py` — no cache hit/miss verification (lines 10-32)
- `tests/test_api_messages_ws.py` — single WS test (lines 1-25)
- `pytest.ini` — current config
- `pyproject.toml` — dev dependency `pytest-asyncio>=1.1.0`
- `AGENTS.md` — Testing Details section (lines 34-43)
- [`.evolution/evol-jwt-refresh.md`](evol-jwt-refresh.md) — prior evolution doc for style reference
