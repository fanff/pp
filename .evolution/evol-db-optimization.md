```yaml
id: evol-db-optimization
status: draft
created: 2026-05-14
authors: []
related: []
supersedes: []
superseded-by: ""
```

## Summary

Optimize six database and caching issues in PP Network's backend: eliminate double-commit and per-user-commit patterns, fix inverted query ordering, add a compound index for pagination, reduce cache TTL on volatile data, and clean up an unused model. No user-facing API changes; all fixes are internal to `ppback/db/dbfuncs.py`, `ppback/routers/messaging.py`, and the schema layer.

## Motivation and context

- **Current behavior** — The following pain points exist in the current codebase:

  1. **`create_convo` double-commit** (`dbfuncs.py:56-72`): commits after inserting the `Conv` row (line 64), then independently commits after adding `ConvMember` rows (line 71). If the member insertion fails after the first commit, the orphan `Conv` row persists.

  2. **`get_messages` inefficient ordering** (`messaging.py:93-104`): queries `ORDER BY ConvoMessage.ts DESC` with `LIMIT n`, then iterates `reversed(results)` in Python to return ascending order. This works but wastes a Python pass and defeats DB-level index ordering.

  3. **Missing compound index on `ConvoMessage`**: single-column indexes exist on `conv_id`, `id`, `ts`, `sender_id`, and `message_type`, but no compound index covers the common pagination query pattern: `WHERE conv_id = ? AND id > ? ORDER BY ts DESC LIMIT ?`. The DB must combine two separate indexes or scan.

  4. **`add_users` commits per user** (`dbfuncs.py:41-53`): iterates `users`, calls `session.add(u)`, then `session.commit()` + `session.refresh(u)` per row. For bulk operations (e.g., seed scripts) this is O(N) round-trips instead of 1.

  5. **5-minute cache TTL on volatile data**: `_hook_user_cached`, `membersof`, and `_get_conversation_list_for_user_cached` all use `@cache(300, ...)`. A user's admin status or role changes can take up to 5 minutes to propagate. Similar staleness risk for conversation membership changes.

  6. **`ConvStartingPoint` table** (`ppdb_schemas.py:58-63`) is defined and migrated but never referenced in any router, DB helper, or test. It appears to be leftover from an earlier design for conversation fork/thread support.

  7. **Migration history** includes 6 files, 3 of which are empty (revisions `190cfa3bcb53`, `1199984eda18`, `e82877344456` — all `pass`). Squashing would simplify the migration chain.

- **Why now** — These are low-risk, high-confidence fixes that improve correctness (transactional integrity), performance (fewer round-trips, better index usage), and maintenance hygiene (dead code, stale cache, noisy migration history). They are safe incremental improvements before larger features land.

- **Constraints** — All DB access goes through `AsyncSession` via `get_db()`; no direct engine usage. Migrations use Alembic with `batch_alter_table` for SQLite compatibility. Cache layer uses `fastapi-cache2` with in-memory backend. Cached functions return `dict` for serialization safety; re-hydration happens in public wrappers.

## Goals

1. **`create_convo` uses a single transaction** — both `Conv` creation and member insertions commit atomically.
2. **`get_messages` queries ASC directly** — remove `reversed()` and sort at the DB level.
3. **`ConvoMessage` gains a composite index** — `(conv_id, id)` for efficient cursor-based pagination, via a new Alembic migration.
4. **`add_users` uses a single commit** — batch-insert all users and commit once.
5. **Cache TTL reduced for volatile data** — evaluate per-function and reduce where appropriate; add cache invalidation hints for membership/role changes.
6. **`ConvStartingPoint` cleaned up** — either remove the model and migration logic, or add a docstring explaining its intended purpose.
7. **Migration history squashed** (optional, stretch goal) — squash the 6 migrations into 1–2 meaningful revisions.

## Non-goals

- No changes to API request/response schemas, `/token` flow, or websocket protocol.
- No changes to the `ConvStartingPoint` table's migration rollback (its `downgrade()` path is already defined and will be updated if we drop the table).
- No changes to the cursor-based pagination semantics: `after` still filters by `id > after` and results are ordered by timestamp. Only the `reversed()` call is removed.
- No switch from `cache(300)` to a different caching library or distributed cache. TTL values may change, but the mechanism stays.
- No introduction of DB-level foreign key ON DELETE CASCADE rules (deferred to a separate evolution).

## User-visible functionality

- **No breaking changes.** All fixes are internal.
- Users may observe slightly faster `get_messages` responses (no Python-side reversal, better index scan).
- Admin role changes and membership changes will propagate faster with reduced cache TTL.
- Bulk user creation (e.g., seed scripts) will be noticeably faster.

## Technical approach

### Baseline (per problem)

| # | Problem | Current code | Location |
|---|---------|-------------|----------|
| 1 | `create_convo` double-commit | `session.add(c1); await session.commit()` then loop + `session.add(cm); await session.commit()` | `dbfuncs.py:62-71` |
| 2 | `get_messages` reversed | `query.order_by(ConvoMessage.ts.desc()).limit(limit)` then `for msg in reversed(results)` | `messaging.py:96,104` |
| 3 | No compound index | Single-column `ix_convomessage_conv_id` and `ix_convomessage_id` on `ConvoMessage` | Migration `d8b3a1c2f4e5` lines 153-161 |
| 4 | `add_users` per-user commit | Loop body: `session.add(u); await session.commit(); await session.refresh(u)` | `dbfuncs.py:45-52` |
| 5 | 300s cache TTL | `@cache(300, key_builder=key_builder)` on 3 functions | `dbfuncs.py:75,110,127` |
| 6 | `ConvStartingPoint` unused | `class ConvStartingPoint(Base)` with `__tablename__ = "conv_starting_points"` | `ppdb_schemas.py:58-63` |
| 7 | Bloated migration history | 6 files, 3 with `pass` only | `alembic/versions/*` |

### Proposed changes

**1. `create_convo` single transaction** (`dbfuncs.py`):

Replace two-phase commit with a single commit after all rows are added:

```python
async def create_convo(...):
    c1 = Conv(label=name)
    session.add(c1)
    await session.flush()  # get c1.id without committing
    for user in users:
        role = "owner" if user.id == creator_id else "member"
        cm = ConvMember(conv_id=c1.id, user_id=user.id, role=role)
        session.add(cm)
    await session.commit()
    await session.refresh(c1)
    return (int(c1.id), str(c1.label))
```

`flush()` assigns the PK and makes it available for FK references without committing. The single `commit()` at the end makes the operation atomic.

**2. `get_messages` ASC ordering** (`messaging.py`):

Change `ORDER BY ts DESC` to `ORDER BY ts ASC` and drop `reversed()`:

```python
results = (
    await session.execute(
        query.order_by(ConvoMessage.ts.asc()).limit(limit)
    )
).scalars().all()

all_results = []
for msg in results:  # no reversed()
    ...
```

Note: this maintains existing behavior because `reversed()` was converting DESC to ASC. The cursor filter `after` with `id > after` combined with `ASC` ordering gives the same logical result for monotonically-increasing IDs.

**3. Compound index** (new migration `alembic/versions/`):

Create migration adding a composite index on `ConvoMessage(conv_id, id)`:

```python
def upgrade():
    with op.batch_alter_table("convomessage") as batch_op:
        batch_op.create_index(
            "ix_convomessage_conv_id_id",
            ["conv_id", "id"],
            unique=False,
        )
```

This directly accelerates the pagination query `WHERE conv_id = ? AND id > ? ORDER BY ... LIMIT ?`.

**4. `add_users` single commit** (`dbfuncs.py`):

Add all users to session, flush to get IDs, commit once:

```python
async def add_users(session, users):
    allu = []
    for k, p in users:
        u = UserInfo(
            name=k, nickname=k, email=f"{k}@{k}",
            salted_password=get_hashed_password(p)
        )
        session.add(u)
        allu.append(u)
    await session.flush()  # assign all IDs
    for u in allu:
        await session.refresh(u)
    await session.commit()
    return allu
```

**5. Cache TTL adjustment** (`dbfuncs.py`):

| Function | Current TTL | Proposed TTL | Rationale |
|----------|-------------|--------------|-----------|
| `_get_conversation_list_for_user_cached` | 300s | 60s | Membership changes need to propagate within ~1 minute |
| `membersof` | 300s | 60s | Same — member role changes should be visible promptly |
| `_hook_user_cached` | 300s | 30s | Admin status changes (e.g., promote/demote) should be fast |
| `allusers` | 300s | 300s | User list rarely changes; keep as-is |
| `user_allowed_in_convo` | 300s | 30s | Convi membership changes should propagate quickly |

Additionally, add targeted cache invalidation in mutation paths:
- In `create_convo`: invalidate `_get_conversation_list_for_user_cached` for all member IDs
- In `accept_friend_request` / `reject_friend_request`: invalidate `_hook_user_cached` for both parties
- When adding/removing conv members: invalidate `membersof` for that conv and `_get_conversation_list_for_user_cached` for affected users

Note: `fastapi-cache2`'s in-memory backend does not support granular key invalidation out of the box. A pragmatic approach is to reduce TTL and add a comment noting that if invalidation becomes a requirement, migrate to a cache backend with explicit `delete()` support (e.g., Redis).

**6. `ConvStartingPoint` cleanup** (`ppdb_schemas.py` and migration):

Option A (recommended): Document the model with a docstring explaining it was designed for future conversation fork/thread support but is not yet wired. Leave the model and table in place. This avoids a destructive migration (schema diff) for a model that does no harm.

Option B: Drop the table via a new migration. This is cleaner but requires a migration that touches a table with no production data risk (likely zero rows). Since the model is tiny and inert, Option A is lower risk.

Recommended approach: Add a docstring to `ConvStartingPoint`:

```python
class ConvStartingPoint(Base):
    """Reserved for future conversation fork/thread support.
    Not yet wired into any router or helper."""
```

**7. Migration squashing** (optional stretch goal):

Merge all 6 migrations into 2:
- Migration 1: initial schema (equivalent to `3f258907f6e5` with `ConvStartingPoint` docstring fix)
- Migration 2: add `is_admin` (equivalent to `a4b6c8d0e1f2`)

Defer to a separate evolution if desired, since squashing is operationally risky on environments with existing DB state.

### Phases

| Phase | Scope | Dependencies | Est. effort |
|-------|-------|-------------|-------------|
| 1 | Items 1+4 (transactional fixes in `dbfuncs.py`) | None | Small |
| 2 | Item 2 (ordering fix in `messaging.py`) | None | Small |
| 3 | Item 3 (compound index in new migration) | Phase 2's ordering change doesn't affect index choice, but confirm together | Small |
| 4 | Item 5 (cache TTL + invalidation hooks) | None | Medium |
| 5 | Item 6 (docstring only) | None | Trivial |
| 6 | Item 7 (squash migrations) | All prior phases | Medium (operational risk) |

Phases 1-5 are independent and can be done in any order. Phase 6 is optional and should be done last.

### Alternatives considered

- **Compound index on `(conv_id, ts)` instead of `(conv_id, id)`**: rejected because the pagination filter uses `id > after`, not `ts > ...`. The `(conv_id, id)` index directly accelerates the WHERE clause. Sorting 1000 rows by `ts` in memory after index scan is negligible.
- **Redis cache backend**: deferred. The in-memory backend is adequate for single-server deployments. If horizontal scaling is needed, a future evolution should replace fastapi-cache2 with Redis.
- **Remove `ConvStartingPoint` table via migration**: deferred (Option B) in favor of docstring-only (Option A). No operational benefit to dropping a zero-row table.
- **Change cursor from `id` to `ts`**: rejected. The `id`-based cursor is well-tested (`test_conversation_messages_after_uses_exclusive_cursor`) and clients depend on it.

### Affected modules

- `ppback/db/dbfuncs.py` — Items 1, 4, 5
- `ppback/routers/messaging.py` — Item 2
- `ppback/db/ppdb_schemas.py` — Item 6 (docstring only)
- `alembic/versions/` — Item 3 (new migration), Item 7 (squash)
- `tests/test_api_convs.py` — verify `create_convo` still works with single commit
- `tests/test_api_messages_ws.py` — verify `get_messages` ordering unchanged
- `tests/conftest.py` — `add_users` and `create_convo` called in fixture setup may benefit from single-commit change

## Auth and websocket compatibility

- **No impact.** `/token` flow, JWT payload, and `/ws` token handshake are untouched.
- The `membersof()` cache change (Item 5) affects which members receive websocket broadcasts — with reduced TTL, membership changes propagate faster to the broadcast path. This is strictly an improvement.
- No changes to `InMemSockets` or the `MessageWS` schema.

## Usability and documentation

- No docs changes required: all changes are internal.
- If a docstring is added to `ConvStartingPoint`, that's self-documenting.
- The `AGENTS.md` section on cached functions should be updated to reflect new TTL values if the evolution is accepted.

## Testability

### Existing test coverage

| Test file | Relevant tests | What it covers |
|-----------|----------------|----------------|
| `tests/test_api_convs.py` | `test_create_conversation_keeps_creator_in_members` | `create_convo` returns correct member list |
| `tests/test_api_messages_ws.py` | `test_conversation_messages_after_uses_exclusive_cursor` | `get_messages` with `after` cursor returns correct subset, ordered ascending |
| `tests/conftest.py` | fixture setup | Calls `add_users` and `create_convo` during seed |

### New/updated tests

1. **`tests/test_db_dbfuncs.py`** (new file):
   - `test_create_convo_is_atomic`: call `create_convo` with deliberately broken member data (e.g., non-existent `UserInfo` object) and assert no orphan `Conv` row exists.
   - `test_add_users_bulk`: call `add_users` with 10 users and assert all are returned with unique IDs and one commit occurred (instrument via `AsyncSession.commit` call count).
   - `test_cache_ttl_values`: read and assert `@cache` TTL annotations match expected values.

2. **`tests/test_api_messages_ws.py`**: add test `test_get_messages_ordering` that:
   - Posts 3 messages with deliberate timestamp offsets (e.g., `time.time() - 100`, `time.time()`, `time.time() + 100`)
   - Calls `GET /conv/{id}/messages?after={first_id}`
   - Asserts results are in ascending timestamp order without `reversed()` artifact.

3. **`tests/test_admin.py`**: verify `is_admin` cache flushes promptly after role change (needs explicit cache invalidation or very short TTL).

### Manual smoke checks

- Start app with `uvicorn ppback.main:app --reload`
- Create a conversation via POST `/conv`, list conversations, post a message, fetch messages — all should work identically to before.

## Complexity and rollout

- **Estimated scope**: Small to Medium (6 independent items, most are <10 line changes).
- **Risk hotspots**:
  - Item 1 (`create_convo`): `flush()` before FK in SQLite + async is well-tested in existing code (`new_msg` endpoint uses `session.flush()` at line 150 of `messaging.py`). Low risk.
  - Item 2 (ordering): must not change result order. Verify with the `after` cursor test.
  - Item 5 (cache TTL): reduced TTL increases DB read load slightly. Acceptable tradeoff for correctness.
- **Rollout plan**: Ship as a single PR with commits organized per phase. Each commit passes existing tests. No feature flags needed.
- **Rollback**: Revert the PR. New migration (compound index) requires a `downgrade()` that drops the index.

## A priori performance analysis

| Change | Expected impact | Validation |
|--------|----------------|------------|
| 1+4 (single commit) | Eliminates N-1 redundant commits per call. `create_convo` with M members: 2 round-trips → 1. `add_users` with N users: N round-trips → 1. | Time `create_convo` and `add_users` with N=100 users; expect ~N× faster. |
| 2 (ASC ordering) | Eliminates Python-side O(N) reversal. Negligible for 1000-row limit but removes an unnecessary pass. | Microbenchmark only if needed. |
| 3 (compound index) | `WHERE conv_id = ? AND id > ?` can now use a single index seek + range scan instead of union of two single-column indexes. Expected to reduce page reads by ~50% on this query. | Check `EXPLAIN QUERY PLAN` on SQLite or `EXPLAIN ANALYZE` on Postgres. |
| 5 (cache TTL) | Increases DB reads for hotspot cached functions by up to 10× (300s→30s). Each function averages 1 lightweight query (< 5ms). Under 100 concurrent users, adds ~5 extra queries/sec. Negligible. | Monitor query throughput if deployed. |

## Risks and open questions

1. **Cache invalidation without Redis**: The `fastapi-cache2` in-memory backend does not expose `delete()` for individual keys. If short TTLs prove insufficient, a future evolution should migrate to Redis-backed caching with explicit invalidation on mutation paths. For now, reduced TTL is adequate.

2. **`ConvStartingPoint` removal**: If the model was intended for a planned feature (forked conversations or threads), removing it could create a diff with future work. Keeping it with a docstring avoids this.

3. **Migration squash timing**: Squashing after the new compound-index migration is added means the squash must include it. If squashing is deferred, the migration chain grows longer, making a future squash harder. Decision: defer squash to a follow-up evolution.

4. **`after` cursor using `id` vs `ts`**: The current `after` parameter uses `id > after` but `ORDER BY ts DESC`. The compound index on `(conv_id, id)` accelerates the WHERE clause, but the sort is still a separate pass. If this becomes a bottleneck, switch the cursor to `ts` and use `(conv_id, ts)` index. Not a priority now.

5. **`ConvoMessage(ts)` index**: Already indexed separately. With `(conv_id, id)` compound index and `ts` single-column index, the query planner can use the `conv_id`-first index for filtering and `ts` index for sort, or the compound index for filtering with an in-memory sort. SQLite/Postgres will choose the optimal plan.

## Decision record

- **Status**: draft
- **Resolution**: *(fill once finalized)*

## References

- `ppback/db/dbfuncs.py` — `add_users` (lines 41-53), `create_convo` (lines 56-72), cached functions (lines 75, 110, 127)
- `ppback/routers/messaging.py` — `get_messages` (lines 72-121), `new_msg` flush pattern (line 150)
- `ppback/db/ppdb_schemas.py` — `ConvStartingPoint` (lines 58-63), `ConvoMessage` (lines 14-23)
- `alembic/versions/3f258907f6e5_.py` — original schema creation
- `alembic/versions/d8b3a1c2f4e5_db_redesign.py` — current `ConvoMessage` indexes (lines 153-161)
- `alembic/versions/a4b6c8d0e1f2_add_is_admin_to_userinfo.py` — latest migration
- `tests/test_api_convs.py` — conversation creation tests
- `tests/test_api_messages_ws.py` — message ordering and cursor tests
- `tests/conftest.py` — test fixture using `add_users` and `create_convo`
- `AGENTS.md` — cached function description, testing details
