---
id: evol-websocket-resilience
status: draft
created: 2026-05-14
authors: [opencode]
related: []
supersedes: []
superseded-by: ""
---

## Summary

Add application-level heartbeat, presence events (online/offline), sender-event
filtering, and proper WebSocket dependency injection to PP Network. Currently
the WebSocket layer is purely in-memory with no connection health checks, no
presence signaling, and a dead-connection leak where stale sockets accumulate
without cleanup. This evolution fixes those gaps in three incremental phases.

## Motivation and context

- **Current behavior**: The `/ws` endpoint at `ppback/routers/ws.py:21-68`
  accepts a connection, waits 5 s for a `{"token": "..."}` packet, authenticates
  via `decode_token` (imported as a raw function, bypassing FastAPI DI), opens
  an ad-hoc `SessionLocal()` instead of using `get_db`, registers the socket
  in `InMemSockets` (`ppback/wsocket.py`), then blocks on `receive_text()` in a
  single-iteration while loop. On disconnect, the socket is removed from the
  in-memory list.
- **Problems**:
  1. **Dead connection leak** — the loop blocks on `receive_text()` with no
     timeout or heartbeat. If the TCP connection drops without a clean
     WebSocket close frame, the server blocks forever and the socket is never
     removed from `InMemSockets.items`. Over time, the 5-socket-per-user limit
     fills with stale entries.
  2. **Sender receives own events** — `messaging.py:155-157` collects
     `usersto_send = [u["user_id"] for u in members]` without filtering out
     `current_user_id`. The broadcast at line 159 sends the `message.created`
     event to every socket of every member including the sender.
  3. **No presence signaling** — clients have no way to know whether other
     conversation members are online/offline. The socket manager tracks live
     connections but never exposes that state.
  4. **WS endpoint bypasses FastAPI DI** — `ws.py` imports `decode_token`
     directly from `ppback.deps` (bypassing `Depends(oauth2_scheme)`) and
     creates `SessionLocal()` ad-hoc instead of using the `get_db` generator.
     This breaks tracing context propagation and makes the WS handler
     inconsistent with every other route.
  5. **Reconnection gap** — server restart wipes all socket state. Clients that
     reconnect have no way to recover missed events without manual polling.
- **Why now**: The existing test (`test_api_messages_ws.py`) demonstrates the
  WS flow works, but it is brittle and missing coverage for multi-client
  scenarios, reconnection, and heartbeat. These gaps become blocker issues as
  the product gains real users.
- **Constraints**: JWT auth flow must remain compatible (<`/token` output,
  `decode_token` return type). The `/ws` handshake must remain a single
  `{"token": "..."}` JSON message for backward compat with existing clients.

## Goals

1. **Heartbeat**: Application-level ping/pong at 30 s intervals. Detect silent
   disconnects within at most 60 s.
2. **Stale-connection cleanup**: Remove socket entries from `InMemSockets` when
   heartbeat fails or the underlying transport is gone.
3. **Sender-event filtering**: The `message.created` broadcast must NOT deliver
   the event to the sender's own sockets.
4. **Presence events**: Broadcast `user.online` and `user.offline` events to
   conversation members when a user's socket count transitions 0→1 or 1→0.
5. **WebSocket DI**: Create a `get_websocket_user` dependency that mirrors
   `decode_token` but works in a WebSocket context, so the WS handler uses
   the same tracing/auth patterns as HTTP routes.
6. **Reconnection protocol**: Clients can reconnect and receive missed presence
   and message-created events since their last known event cursor.
7. **Tests**: Cover heartbeat failure, sender filtering, presence broadcast,
   reconnection, and multi-client scenarios.

## Non-goals

- **Persistent outbox / exactly-once delivery**: The reconnection protocol is
  best-effort (at-least-once with client-side dedup). Guaranteed delivery is
  deferred.
- **Horizontal scaling / WS sticky-sessions**: `InMemSockets` remains process-
  local. Multi-process or multi-host deployment requires a separate evolution.
- **Presence history or "last seen" timestamps**: Presence is ephemeral — no
  DB storage of online/offline transitions.
- **Server-side message content in WS events**: The `message.created` event
  continues to carry only metadata (`conversation_id`, `message_id`,
  `sender_id`, `ts`). Clients fetch content via `GET /conv/{id}/messages`.
- **Rate limiting or DoS protection for WS connections**: Deferred to a future
  evolution.
- **Auth rate limiting on `/ws`**: Not in scope.

## User-visible functionality

### Additive (no breaking changes)

| Feature | Description |
|---------|-------------|
| Heartbeat | Server sends `{"type": "ping"}` every 30 s; client responds with `{"type": "pong"}` within 10 s or connection is closed. Backward-compat: clients that ignore unknown message types continue to work (the server will disconnect them after a grace period). |
| Sender filtering | Message sender no longer receives their own `message.created` event via WS. |
| Presence events | When a user goes online (first socket): `{"type": "user.online", "user_id": N, "ts": T}` broadcast to all conversation members. When offline (last socket dropped): `{"type": "user.offline", "user_id": N, "ts": T}`. |
| Reconnection | Client sends `{"token": "<jwt>", "last_event_id": N}` on reconnect. Server replays missed `message.created` and presence events with `event_id > N` (stored in-memory event ring buffer, last 100 events). |

### Breaking changes

- **None**, provided existing clients use a JSON parser that ignores unknown
  fields. The `{"token"}` handshake is unchanged. The new `"last_event_id"`
  field is optional (absent → no replay).

## Technical approach

### Baseline flow (current)

```
Client → Server: opens /ws
Server → Client: accept
Client → Server: {"token": "<jwt>"}        (within 5 s)
Server: decode_token(jwt) → user_id
Server: SessionLocal(), hook_user()
Server: InMemSockets.add_user(user_id, ws)
Server: while True: await ws.receive_text()
        → no timeout, no heartbeat
        → on disconnect: InMemSockets.drop_user()
        → return (single iteration — see bug #1 below)
```

**Known bugs in current loop:**
1. The `return` inside `while keep_user_connected` causes the loop to execute
   at most once — if `receive_text()` returns normally (client sent a message),
   the function exits. The "keep connected" loop is effectively dead code.
2. The `finally` block calls `drop_user()` unconditionally — even on a clean
   message receive — so a working connection that receives a message gets its
   socket removed. (The `return` after `finally` masks this because the
   function exits anyway, but the entry is already gone.)

### Phase 1 — Heartbeat, sender filtering, and WS DI (small)

**WebSocket DI** (`ppback/deps.py`):

Add a `get_ws_user` dependency that accepts a `WebSocket` directly (not via
`OAuth2PasswordBearer`) and returns the authenticated `user_id`:

```python
async def get_ws_user(websocket: WebSocket) -> int:
    try:
        data = await asyncio.wait_for(websocket.receive_json(), timeout=5)
    except (asyncio.TimeoutError, KeyError, json.JSONDecodeError):
        await websocket.close(code=1008)
        raise
    token: str = data["token"]
    user_id = int(jwt.decode(token, key=MASTER_SECRET_KEY,
                              algorithms=["HS256"])["user_id"])
    return user_id
```

This mirrors `decode_token` but adapted for the WS context. It avoids importing
the `OAuth2PasswordBearer` scheme (which requires an HTTP request). The session
is still resolved manually or via a second dependency.

**Alternative** (simpler): Keep `decode_token`'s JWT logic as-is, but call it
from the WS handler with the raw token string (bypassing `Depends(oauth2_scheme
)`). This is what the current code already does — the only change is to use
`get_db` for the session.

**Decision**: Use a dedicated `get_ws_user` in `deps.py` that reuses the
`jwt.decode` call but does not depend on `OAuth2PasswordBearer`. Keep the
session acquisition manual (a 2-line `async with SessionLocal()`) to avoid the
complexity of a `Depends` chain inside a WebSocket handler — FastAPI does not
support `Depends` in WebSocket routes the same way as HTTP routes.

**Fix sender filtering** (`ppback/wsocket.py` and `ppback/routers/messaging.py`):

Option A — filter in `broadcast_message_to_users`:
```python
async def broadcast_message_to_users(self, from_user_id, convo_id,
                                      user_ids, msg_id, ts):
    # filter out the sender
    target_ids = [uid for uid in user_ids if uid != from_user_id]
    for websocket in self.get_sockets_for_many(target_ids):
        ...
```

Option B — filter at the call site in `messaging.py`:
```python
members = await membersof(session, convo_id)
usersto_send = [u["user_id"] for u in members if u["user_id"] != current_user_id]
```

**Decision**: Option B (call site) because `broadcast_message_to_users` already
receives `from_user_id` and may want to use it for analytics in the future.
Applying the filter at both is belt-and-suspenders: filter at the call site
for clarity, and add a guard in the broadcast as a safety net.

**Heartbeat** (`ppback/wsocket.py` or `ppback/routers/ws.py`):

Add a `heartbeat` task per connection:

```python
async def _heartbeat(websocket: WebSocket) -> None:
    """Send ping every 30 s, close if no pong within 10 s."""
    while True:
        await asyncio.sleep(30)
        try:
            await asyncio.wait_for(
                websocket.send_json({"type": "ping"}), timeout=5
            )
            pong = await asyncio.wait_for(
                websocket.receive_json(), timeout=10
            )
            if not isinstance(pong, dict) or pong.get("type") != "pong":
                await websocket.close(code=1008)
                return
        except (asyncio.TimeoutError, WebSocketDisconnect, RuntimeError):
            await websocket.close(code=1008)
            return
```

The WS handler spawns this as a Task (via `asyncio.create_task`) and cancels
it on disconnect. The main loop changes from `receive_text()` to a select-loop
that listens for both client messages and cancellation.

**Revised WS handler** (`ppback/routers/ws.py`):

```python
@router.websocket("/ws")
async def websocket_endpoint(websocket: fastapi.WebSocket):
    await websocket.accept()
    user_id = await get_ws_user(websocket)
    user = await hook_user(...)  # with a session
    idx = inmemsockets.add_user(user_id, websocket)
    hb_task = asyncio.create_task(_heartbeat(websocket))

    try:
        while True:
            try:
                data = await asyncio.wait_for(
                    websocket.receive_json(), timeout=35
                )
                # handle client messages (pong, etc.)
                if data.get("type") == "pong":
                    continue
            except asyncio.TimeoutError:
                # heartbeat task handles this
                continue
            except (WebSocketDisconnect, RuntimeError):
                break
    finally:
        hb_task.cancel()
        inmemsockets.drop_user(user_id, idx)
```

**Stale-connection cleanup**: The heartbeat Task guarantees that a dead
connection is detected within at most 40 s (30 s sleep + 10 s pong wait) and
the `finally` block removes the socket entry. No separate scavenger needed.

**Remove the buggy single-iteration loop**: The `while keep_user_connected`
variable and the misplaced `return` are replaced with the proper infinite loop
above.

**Affected modules (Phase 1):**

| Module | Change |
|--------|--------|
| `ppback/routers/ws.py` | Rewrite handler with heartbeat, proper loop, session via `get_db`, call `get_ws_user` |
| `ppback/wsocket.py` | Add `filter_sender` parameter or rely on call-site filtering |
| `ppback/routers/messaging.py` | Filter `current_user_id` from `usersto_send` |
| `ppback/deps.py` | Add `get_ws_user` function (JWT decode without OAuth2 scheme) |
| `ppback/ppschema.py` | Add `PingPong` schema or extend `MessageWS` with `ping`/`pong` types |

### Phase 2 — Presence events (medium)

**Schema additions** (`ppback/ppschema.py`):

```python
class PresenceEvent(BaseModel):
    type: Literal["user.online", "user.offline"]
    user_id: int
    ts: float
```

The existing `MessageWS` continues to be used for `message.created`. Presence
events use a separate `PresenceEvent` schema.

**InMemSockets changes** (`ppback/wsocket.py`):

Track online/offline transitions. Add a method that returns the set of
conversation members for a given user (the broadcast target list needs to be
supplied by the caller — InMemSockets does not have access to the DB).

```python
class InMemSockets:
    # existing fields...
    _prev_count: Dict[int, int] = {}  # user_id → previous socket count

    async def _broadcast_presence(
        self,
        user_id: int,
        event_type: Literal["user.online", "user.offline"],
        target_user_ids: List[int],
        ts: float,
    ):
        event = PresenceEvent(type=event_type, user_id=user_id, ts=ts)
        payload = event.model_dump_json()
        for ws in self.get_sockets_for_many(target_user_ids):
            await self._safe_send(ws, payload)
```

The WS handler, after adding or removing a socket, checks the transition:

```python
prev = inmemsockets.count_for_user(user_id)
inmemsockets.add_user(user_id, websocket)
curr = inmemsockets.count_for_user(user_id)
if prev == 0 and curr > 0:
    members = await _get_conversation_members_for_user(session, user_id)
    asyncio.create_task(
        inmemsockets._broadcast_presence(
            user_id, "user.online", members, time.time()
        )
    )
```

(Same for 1→0 transition in `drop_user`.)

**MessageWS type union** (`ppback/ppschema.py`):

Clients receive either `MessageWS` or `PresenceEvent` on the wire. The
dispatcher on the client side already uses `type` field for routing, so no
server-side union schema is needed — just document the two possible shapes.

**Affected modules (Phase 2):**

| Module | Change |
|--------|--------|
| `ppback/ppschema.py` | Add `PresenceEvent` model; extend `MessageWS.type` literal union |
| `ppback/wsocket.py` | Add `_broadcast_presence`, transition detection helpers |
| `ppback/routers/ws.py` | Hook transition events on add/drop; resolve broadcast targets via DB |

### Phase 3 — Reconnection protocol (medium)

**In-memory event ring buffer** (`ppback/wsocket.py` or a new
`ppback/wsevents.py`):

Maintain a process-local ring buffer of recent events:

```python
from collections import deque
from dataclasses import dataclass

@dataclass
class WSEvent:
    event_id: int
    type: str
    payload: dict
    ts: float

class EventBuffer:
    MAX_SIZE = 100

    def __init__(self):
        self._events: deque[WSEvent] = deque(maxlen=self.MAX_SIZE)
        self._counter = 0

    def push(self, type: str, payload: dict) -> int:
        self._counter += 1
        self._events.append(WSEvent(self._counter, type, payload, time.time()))
        return self._counter

    def since(self, event_id: int) -> List[WSEvent]:
        return [e for e in self._events if e.event_id > event_id]
```

**Integration**: `broadcast_message_to_users` and `_broadcast_presence` push
to `EventBuffer` after sending, recording `event_id`. The presence broadcast
targets include all relevant conversation members.

**Reconnection in WS handler** (`ppback/routers/ws.py`):

During handshake, accept an optional `last_event_id`:

```python
data = await websocket.receive_json()
token = data["token"]
last_event_id = data.get("last_event_id")  # optional
user_id = get_ws_user_from_token(token)     # simplified call

# after auth and socket registration:
if last_event_id is not None:
    missed = event_buffer.since(last_event_id)
    for ev in missed:
        await websocket.send_json(ev.payload)
```

**Limitation**: The ring buffer is process-local and in-memory. A server
restart clears it, so reconnecting after a restart always starts from
`last_event_id = None`. This is acceptable for a single-process deployment.

**Affected modules (Phase 3):**

| Module | Change |
|--------|--------|
| `ppback/wsevents.py` **new** | `EventBuffer` ring buffer |
| `ppback/wsocket.py` | Push to `EventBuffer` after broadcast |
| `ppback/routers/ws.py` | Accept `last_event_id`, replay missed events on reconnect |
| `ppback/ppschema.py` | No change (replayed events use existing schemas) |

### Alternatives considered

- **OS-level TCP keepalive** (`TCP_KEEPIDLE`, `TCP_KEEPINTVL`): Unreliable
  across cloud load balancers and less configurable. Application-level
  heartbeat is preferred.
- **External pub/sub (Redis) for presence**: Overkill for single-process
  deployment. Can be introduced later if horizontal scaling is needed.
- **DB-persisted presence**: Adds write pressure to the DB for ephemeral
  state. In-memory is sufficient.
- **Server-sent events (SSE) instead of full WS**: Would still need a
  persistent connection, but loses bidirectional communication (no pong
  from client). WS is the right choice given existing infrastructure.
- **Auto-reconnect in client SDK without server changes**: Leaves the stale
  socket leak unfixed. Server must drive heartbeat to detect dead peers.

## Auth and websocket compatibility

- **`/token` response**: Unchanged. No new fields.
- **JWT payload**: Unchanged. `decode_token` and `get_ws_user` both decode
  the same `{"user_id": int}` payload with `HS256`.
- **`/ws` handshake protocol**: The `{"token": "..."}` first message is
  preserved. The optional `"last_event_id"` field is additive. Clients that
  omit it continue to work (no event replay on reconnect).
- **New message types**: Clients must be updated to handle `"ping"`, `"pong"`,
  `"user.online"`, and `"user.offline"` message types. Old clients that use
  a JSON parser will see unknown `type` values and can safely ignore them, but
  they will not receive presence information. The server will disconnect
  clients that do not respond to `"ping"` (after a grace period of ~40 s).
- **Backward compatibility window**: During a transition period, the server
  could skip heartbeat for connections that do not respond to the first ping.
  However, the whole point is to detect dead connections — so a grace period
  of 2 missed pings (80 s) before forced close is recommended.
- **Session handling**: `get_ws_user` in `deps.py` bypasses `OAuth2PasswordBearer`
  but uses the same `jwt.decode` call with the same `MASTER_SECRET_KEY`. There
  is no difference in token validation.

## Usability and documentation

- **Event types**: Document the complete WS message catalog in `README.md`:
  `message.created`, `user.online`, `user.offline`, `ping`, `pong`.
- **Reconnection guide**: Add a how-to section for client authors covering:
  - Storing `last_event_id` from each received event
  - Sending `{"token": "<jwt>", "last_event_id": N}` on reconnect
  - Fetching missed message content via `GET /conv/{id}/messages?after=N`
  - Handling heartbeat (responding to `{"type":"ping"}` with `{"type":"pong"}`)
- **Error messaging**: `WebSocketDisconnect` with code `1008` indicates policy
  violation (failed auth or heartbeat timeout). Document this so clients can
  differentiate from normal closure.

## Testability

### Phase 1 tests

| Test | File | What it validates |
|------|------|-------------------|
| Heartbeat close on missing pong | `test_api_messages_ws.py` | Server closes connection after missing pong response |
| Heartbeat continues on valid pong | `test_api_messages_ws.py` | Connection stays open when client sends `{"type":"pong"}` |
| Sender does not receive own event | `test_api_messages_ws.py` | Open two WS connections (same user, two tokens), post message, only the "other" token's socket receives the event |
| Stale socket removed from InMemSockets | `test_api_messages_ws.py` | After heartbeat-induced close, `inmemsockets.count_for_user()` returns 0 |
| WS auth via `get_ws_user` | `test_api_messages_ws.py` | Invalid token returns 1008 close; valid token proceeds |

### Phase 2 tests

| Test | File | What it validates |
|------|------|-------------------|
| `user.online` broadcast on first socket | `test_api_messages_ws.py` | Alice connects → Bob's socket (shared conversation) receives `{"type":"user.online","user_id":1}` |
| `user.offline` broadcast on last socket close | `test_api_messages_ws.py` | Alice disconnects last socket → Bob receives `{"type":"user.offline","user_id":1}` |
| No presence event when socket count stays >0 | `test_api_messages_ws.py` | Alice opens second socket → no `user.online` event (already online) |
| Presence scope limited to conversation members | `test_api_messages_ws.py` | Diana (no shared conv with Alice) does NOT receive presence events for Alice |

### Phase 3 tests

| Test | File | What it validates |
|------|------|-------------------|
| Reconnect replays missed events | `test_api_messages_ws.py` | Disconnect, reconnect with `last_event_id=N`, receive events with `event_id > N` |
| Reconnect with no `last_event_id` | `test_api_messages_ws.py` | Normal connection works without replay |
| Ring buffer limit | `test_api_messages_ws.py` | Events beyond `MAX_SIZE` (100) are not replayed |
| Server restart loses buffer | `test_api_messages_ws.py` | After restart, reconnect with `last_event_id` returns no replayed events |

### Fixture changes

- `tests/conftest.py`: No structural change. Existing fixtures already provide
  tokens for all four test users. New WS tests can open multiple concurrent
  connections via `client.websocket_connect("/ws")`.
- `inmemsockets` should be reset between tests (add `inmemsockets.items.clear()`
  to fixture teardown or test setup).

### Manual smoke check

```bash
# boot the server
uvicorn ppback.main:app --lifespan=on

# Use a WebSocket client (e.g., websocat or a custom script) to test:
# 1. Connect with valid token → gets accepted
# 2. Receive ping within 30 s → respond with pong
# 3. Connect with invalid token → gets 1008 close
# 4. Connect two clients, post message → only non-sender receives event
# 5. Disconnect one client → other clients receive user.offline
```

## Complexity and rollout

- **Scope**: M (medium) across all three phases.
  - Phase 1: S (~100 lines changed across 4 files)
  - Phase 2: S (~80 lines across 3 files)
  - Phase 3: M (~150 lines including new `wsevents.py`)

- **Risk hotspots**:
  1. **Heartbeat Task lifecycle**: If the heartbeat Task crashes without
     cancellation, the socket entry leaks. Mitigation: wrap the heartbeat body
     in try/except and always close the socket on error.
  2. **Presence broadcast target resolution**: Resolving "who should receive
     this presence event" requires querying DB for conversation members.
     Mitigation: cache conversation membership (existing cache layer in
     `dbfuncs.py`), or limit presence broadcast to friends only (simpler).
  3. **Ring buffer memory**: 100 events at ~200 bytes each = 20 KB. Negligible.
  4. **Concurrent socket add/remove**: `InMemSockets` uses a plain `list` with
     no locking. Mitigation: use `asyncio.Lock` around mutations if contention
     is observed (unlikely at current scale).

- **Dependencies**: Phase 1 is a prerequisite for Phase 2 (presence relies on
  accurate socket-count tracking). Phase 3 depends on Phase 1 and 2
  (reconnection replay needs heartbeat to detect disconnects and presence
  events to replay).

- **Rollback**: Revert each phase independently. Phase 1 can be rolled back
  without affecting Phase 2 or 3 code if those are not yet deployed. Reverting
  Phase 1 restores the old dead-connection behavior but keeps existing clients
  functional.

## A priori performance analysis

| Hot path | Current cost | After Phase 1 | After Phase 2 | After Phase 3 |
|----------|-------------|---------------|---------------|---------------|
| `/usermsg` broadcast | `O(N_sockets)` fan-out send | Same, minus sender sockets (~10% reduction avg) | Same as Phase 1 | Same + `EventBuffer.push` (O(1) deque append) |
| WS connection lifecycle | `O(1)` add/remove | +1 Task spawn per connection (~50 µs) | +1 DB query per transition for membership resolution | +1 DB query on reconnect for missed events |
| WS idle (per second) | `O(0)` — blocked on `recv` | `O(1)` heartbeat timer wakeup every 30 s | Same | Same |
| Memory per connection | 1 socket reference | 1 Task handle + 1 socket ref | Same | Same |
| Memory (ring buffer) | 0 | 0 | 0 | ~20 KB (100 events) |

**Hypothesis**: Phase 1 adds ~50 µs per connection lifecycle for Task creation.
Phase 2 adds one DB query per online/offline transition (rare). Phase 3 adds
one DB query per reconnect (rare) and O(1) deque push per event. Total impact
is negligible.

**Validation**: Run `pytest -k ws` before and after each phase and compare
runtime. For manual validation, use `timeout 5 uvicorn ...` boot test.

## Risks and open questions

1. **Heartbeat interval**: 30 s ping / 40 s timeout is conservative. Should it
   be configurable via env var (`WS_HEARTBEAT_INTERVAL`, `WS_HEARTBEAT_TIMEOUT`)?
   **Yes — add env vars with defaults.**
2. **Presence broadcast target**: Should presence go to all conversation members
   or only friends? **Conversation members** is more useful for a chat app but
   requires a DB query. Consider caching conversation membership.
3. **Ring buffer sizing**: 100 events fits typical reconnect windows. Should it
   be configurable? **Yes — env var `WS_EVENT_BUFFER_SIZE` defaulting to 100.**
4. **Event ID monotonicity**: The `EventBuffer._counter` resets on server
   restart. A client reconnecting with `last_event_id=95` from a previous
   server instance will get 0 missed events (since the new counter starts at 0
   and no event has ID > 95). This is acceptable — the client should fall back
   to REST API for catch-up.
5. **Concurrent test runs**: The `inmemsockets` global singleton is shared
   across tests. Must add a reset mechanism in `conftest.py` to avoid test
   interference.

## Decision record

- **Status**: draft
- **Resolution**: —

## References

- `ppback/routers/ws.py:21-68` — current WS handler (no heartbeat, broken loop)
- `ppback/wsocket.py:14-82` — `InMemSockets` (no presence, no event buffer)
- `ppback/routers/messaging.py:155-165` — broadcast call site (sends to sender)
- `ppback/ppschema.py:38-44` — `MessageWS` schema (single event type)
- `ppback/deps.py:33-41` — `decode_token` (currently imported raw in ws.py)
- `ppback/deps.py:22-30` — `get_db` session generator (not used in ws.py)
- `tests/test_api_messages_ws.py:1-55` — existing WS tests (single-client only)
- `tests/conftest.py:25-121` — fixture seeding and token setup
