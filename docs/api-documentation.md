# PP Network - API Documentation

## Base URL

All endpoints are served under the app root, typically `http://localhost:8000`.

## Authentication

### POST `/token` — Login

Authenticate with username/password and receive a JWT token.

| Field | Type | Location | Description |
|-------|------|----------|-------------|
| `username` | string | form | Username |
| `password` | string | form | Password |
| `grant_type` | string | form | Must be `password` |

**Response `200`:**
```json
{
  "access_token": "<jwt>",
  "token_type": "bearer"
}
```

The JWT is signed with HS256 using `MASTER_SECRET_KEY`. The decoded payload contains `user_id` (int). All subsequent requests use `Authorization: Bearer <token>`.

---

## Authentication Required

All endpoints below require `Authorization: Bearer <token>`. Unless specified, the `decode_token` dependency extracts `user_id` from the JWT.

---

## Users

### GET `/users` — List visible users

Returns users visible to the authenticated user: friends, conversation peers, pending request senders, and self.

**Response `200`:**
```json
[
  { "id": 1, "name": "alice", "nickname": "alice" },
  { "id": 2, "name": "bob", "nickname": "bob" }
]
```

| Field | Type | Description |
|-------|------|-------------|
| `id` | int | User ID |
| `name` | string | Username |
| `nickname` | string | Display nickname |

---

## Invite Codes

### POST `/invite-codes` — Create invite code

Generates a `secrets.token_urlsafe(16)` invite code for the current user.

**Request body:** none

**Response `200`:**
```json
{ "code": "abc123..." }
```

| Field | Type | Description |
|-------|------|-------------|
| `code` | string | 22-character URL-safe invite code |

---

## Friend Requests

### POST `/friend-requests` — Submit invite code

Sends a friend request to the creator of an invite code.

**Request body:**
```json
{ "invite_code": "abc123..." }
```

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `invite_code` | string | yes | A valid, unused invite code |

**Response `200`:**
```json
{
  "id": 1,
  "from_user_id": 2,
  "to_user_id": 1,
  "status": "pending"
}
```

| Field | Type | Description |
|-------|------|-------------|
| `id` | int | Friend request ID |
| `from_user_id` | int | ID of the requesting user |
| `to_user_id` | int | ID of the target user |
| `status` | string | `"pending"` |

**Error `400`:** Invalid or expired invite code.

---

### GET `/friend-requests` — List friend requests

Returns friend requests where the current user is the sender or recipient.

**Response `200`:**
```json
[
  {
    "id": 1,
    "from_user_id": 2,
    "to_user_id": 1,
    "status": "pending"
  }
]
```

| Field | Type | Description |
|-------|------|-------------|
| `id` | int | Friend request ID |
| `from_user_id` | int | Sender ID |
| `to_user_id` | int | Recipient ID |
| `status` | string | `"pending"`, `"accepted"`, or `"rejected"` |

---

### POST `/friend-requests/{request_id}/accept` — Accept friend request

Accepts a pending friend request addressed to the current user.

| Parameter | Type | Location | Description |
|-----------|------|----------|-------------|
| `request_id` | int | path | ID of the friend request |

**Response `200`:**
```json
{
  "user_id": 2,
  "name": "bob",
  "nickname": "bob",
  "since": 1712345678.123
}
```

| Field | Type | Description |
|-------|------|-------------|
| `user_id` | int | ID of the other user in the friendship |
| `name` | string | Username |
| `nickname` | string | Display nickname |
| `since` | float | Unix timestamp of when the friendship was created |

---

### POST `/friend-requests/{request_id}/reject` — Reject friend request

Rejects a pending friend request addressed to the current user.

| Parameter | Type | Location | Description |
|-----------|------|----------|-------------|
| `request_id` | int | path | ID of the friend request |

**Response `200:**
```json
{ "status": "rejected" }
```

---

## Friends

### GET `/friends` — List friends

Returns all accepted friendships for the current user.

**Response `200`:**
```json
[
  {
    "user_id": 2,
    "name": "bob",
    "nickname": "bob",
    "since": 1712345678.123
  }
]
```

Response fields are the same as `FriendshipOut`: `user_id`, `name`, `nickname`, `since`.

---

## Conversations

### POST `/conv` — Create conversation

Creates a new conversation. The creator is automatically added as an `owner` if not included in `members`.

**Request body:**
```json
{
  "label": "My Chat",
  "members": [1, 2, 3]
}
```

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `label` | string | yes | Conversation name |
| `members` | array[int] | yes | List of user IDs to add as members |

**Response `200`:**
```json
{
  "id": 1,
  "label": "My Chat",
  "members": [1, 2, 3]
}
```

| Field | Type | Description |
|-------|------|-------------|
| `id` | int | Conversation ID |
| `label` | string | Conversation name |
| `members` | array[int] | All member user IDs |

---

### GET `/conv` — List conversations

Returns all conversations the current user is a member of.

**Cached:** 5 minutes TTL.

**Response `200`:**
```json
{
  "conversations": [
    { "id": 1, "label": "General", "members": [1, 2] },
    { "id": 2, "label": "My Chat", "members": [1, 2, 3] }
  ]
}
```

| Field | Type | Description |
|-------|------|-------------|
| `id` | int | Conversation ID |
| `label` | string | Conversation name |
| `members` | array[int] | Member user IDs |

---

### GET `/conv/{conversation_id}/messages` — Get messages

Retrieves messages from a conversation. Requires membership.

| Parameter | Type | Location | Required | Default | Description |
|-----------|------|----------|----------|---------|-------------|
| `conversation_id` | int | path | yes | — | Conversation ID |
| `limit` | int | query | no | 1000 | Max messages to return |
| `after` | int | query | no | — | Exclusive cursor: return only messages with `id > after` |

**Response `200`:**
```json
[
  {
    "id": 1,
    "content": "Hello!",
    "sender": 1,
    "message_type": "text",
    "ts": 1712345678.123
  }
]
```

| Field | Type | Description |
|-------|------|-------------|
| `id` | int | Message ID |
| `content` | string | Message text content |
| `sender` | int | User ID of the sender |
| `message_type` | string | Message type: `"text"`, `"image"`, `"audio"`, or `"custom"` |
| `ts` | float | Unix timestamp |

Messages are returned in ascending chronological order.

---

## Messages

### POST `/usermsg` — Send message

Posts a message to a conversation. Requires membership and a write-allowed role (`owner`, `admin`, or `member`).

**Request body:**
```json
{
  "content": "Hello everyone!",
  "conversation_id": 1
}
```

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `content` | string | yes | Message text |
| `conversation_id` | int | yes | Target conversation ID |

**Response `200`:**
```json
{
  "status": "ok",
  "messageid": 42
}
```

| Field | Type | Description |
|-------|------|-------------|
| `status` | string | `"ok"` on success |
| `messageid` | int \| null | ID of the created message |

**WebSocket broadcast:** After saving, the server broadcasts a `message.created` event to all connected WebSocket sockets of conversation members. See WebSocket section.

---

## WebSocket

### `ws://<host>/ws` — Real-time events

**Connection handshake:**

1. Client opens a WebSocket connection.
2. Client sends a JSON message within 5 seconds:
   ```json
   { "token": "<jwt>" }
   ```
3. Server validates the JWT, looks up the user, and registers the socket.
4. If no valid auth message is received within 5 seconds, the server closes the connection.

**Concurrency limit:** Maximum 5 sockets per user.

**Inbound messages:** The server reads incoming messages to keep the connection alive but does not process them. All client-to-server communication uses REST endpoints.

**Outbound events:**

When a message is posted via `POST /usermsg`, the server broadcasts to all connected members:
```json
{
  "type": "message.created",
  "conversation_id": 1,
  "message_id": 42,
  "sender_id": 1,
  "ts": 1712345678.123
}
```

| Field | Type | Description |
|-------|------|-------------|
| `type` | string | Always `"message.created"` |
| `conversation_id` | int | Conversation where the message was posted |
| `message_id` | int | ID of the new message |
| `sender_id` | int | ID of the sender |
| `ts` | float | Unix timestamp |

Note: Message `content` is **not** included in WebSocket events. Clients fetch the full message content via `GET /conv/{id}/messages`.

---

## Admin (requires `is_admin` flag)

All admin endpoints are gated by `require_admin`, which checks `UserInfo.is_admin`. A non-admin user receives **403 Forbidden**.

### GET `/admin/users` — List all users

**Response `200`:**
```json
[
  {
    "id": 1,
    "name": "admin",
    "nickname": "admin",
    "is_admin": true,
    "created_at": 1712345678.123
  }
]
```

| Field | Type | Description |
|-------|------|-------------|
| `id` | int | User ID |
| `name` | string | Username |
| `nickname` | string | Display nickname |
| `is_admin` | bool | Admin flag |
| `created_at` | float \| null | Unix timestamp of account creation |

---

### POST `/admin/users/{user_id}/role` — Set user role

Promotes or demotes a user's admin status.

| Parameter | Type | Location | Description |
|-----------|------|----------|-------------|
| `user_id` | int | path | Target user ID |

**Request body:**
```json
{ "is_admin": true }
```

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `is_admin` | bool | yes | `true` to grant admin, `false` to revoke |

**Response `200`:**
```json
{
  "status": "ok",
  "user_id": 3,
  "is_admin": true
}
```

**Error `404`:** User not found.

---

### GET `/admin/conv` — List all conversations

**Response `200`:**
```json
[
  {
    "id": 1,
    "label": "General",
    "member_count": 2,
    "created_at": 1712345678.123
  }
]
```

| Field | Type | Description |
|-------|------|-------------|
| `id` | int | Conversation ID |
| `label` | string | Conversation name |
| `member_count` | int | Number of members |
| `created_at` | float \| null | Unix timestamp of creation |

---

### POST `/admin/conv/{conv_id}/members/{user_id}/role` — Set member role within conversation

Changes a member's role in a conversation.

| Parameter | Type | Location | Description |
|-----------|------|----------|-------------|
| `conv_id` | int | path | Conversation ID |
| `user_id` | int | path | Member user ID |

**Request body:**
```json
{ "role": "viewer" }
```

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `role` | string | yes | One of: `owner`, `admin`, `member`, `viewer` |

**Response `200`:**
```json
{
  "status": "ok",
  "conv_id": 1,
  "user_id": 3,
  "role": "viewer"
}
```

**Error `404`:** Conversation, user, or membership not found.
**Error `400`:** Invalid role value.

---

## Schema Reference

### Request Schemas

| Schema | Fields | Used By |
|--------|--------|---------|
| `MsgInputSchema` | `content: str`, `conversation_id: int` | `POST /usermsg` |
| `ConversationCreate` | `label: str`, `members: list[int]` | `POST /conv` |
| `FriendRequestSubmit` | `invite_code: str` | `POST /friend-requests` |
| `InviteCodeCreate` | _(empty)_ | `POST /invite-codes` |
| `FriendRequestAccept` | _(empty)_ | `POST /friend-requests/{id}/accept` |
| `AdminSetRoleRequest` | `is_admin: bool` | `POST /admin/users/{id}/role` |
| `AdminSetConvMemberRoleRequest` | `role: str` | `POST /admin/conv/{conv_id}/members/{user_id}/role` |

### Response Schemas

| Schema | Fields |
|--------|--------|
| `MsgOutputSchema` | `status: str`, `messageid: int \| null` |
| `MessageSchema` | `id: int`, `content: str`, `sender: int`, `message_type: str`, `ts: float` |
| `MessageWS` | `type: "message.created"`, `conversation_id: int`, `message_id: int`, `sender_id: int`, `ts: float` |
| `ConversationItem` | `id: int`, `label: str`, `members: list[int]` |
| `ConversationList` | `conversations: list[ConversationItem]` |
| `InviteCodeOut` | `code: str` |
| `FriendRequestOut` | `id: int`, `from_user_id: int`, `to_user_id: int`, `status: str` |
| `FriendshipOut` | `user_id: int`, `name: str`, `nickname: str`, `since: float` |
| `AdminUserOut` | `id: int`, `name: str`, `nickname: str`, `is_admin: bool`, `created_at: float \| null` |
| `AdminConvOut` | `id: int`, `label: str`, `member_count: int`, `created_at: float \| null` |

---

## Conversation Roles

| Role | Write Permission | Description |
|------|-----------------|-------------|
| `owner` | Yes | Creator; has full control |
| `admin` | Yes | Can write messages |
| `member` | Yes | Can write messages |
| `viewer` | No | Read-only access |

---

## Complete Endpoint Table

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| POST | `/token` | None | Login |
| GET | `/users` | JWT | List visible users |
| POST | `/invite-codes` | JWT | Generate invite code |
| POST | `/friend-requests` | JWT | Submit invite code |
| GET | `/friend-requests` | JWT | List friend requests |
| POST | `/friend-requests/{id}/accept` | JWT | Accept friend request |
| POST | `/friend-requests/{id}/reject` | JWT | Reject friend request |
| GET | `/friends` | JWT | List friends |
| POST | `/conv` | JWT | Create conversation |
| GET | `/conv` | JWT | List conversations |
| GET | `/conv/{id}/messages` | JWT | Get messages |
| POST | `/usermsg` | JWT | Send message |
| WS | `/ws` | JWT handshake | Real-time events |
| GET | `/admin/users` | Admin | List all users |
| POST | `/admin/users/{id}/role` | Admin | Set admin role |
| GET | `/admin/conv` | Admin | List all conversations |
| POST | `/admin/conv/{cid}/members/{uid}/role` | Admin | Set member role |
