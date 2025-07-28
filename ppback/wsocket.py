import asyncio
import logging
from typing import List, Tuple

import fastapi
from opentelemetry import trace

from ppback.ppschema import MessageWS

tracer = trace.get_tracer(__name__)
logger = logging.getLogger("ppback.wsocket")


class InMemSockets:
    """Keeping sockets open, in a global memory object."""

    def __init__(self, limit=5):
        """Initialize the InMemSockets with a limit on concurrent connections."""
        # This is a list of [user_id, socket, idx]
        self.items: List[Tuple[int, fastapi.WebSocket, int]] = []
        # limit the number of concurrent connections per user
        self.limit = limit
        # this is a simple index to give a unique id to each socket
        self.idx = 0

    def gen_idx(self):
        """Generate a new index for the socket."""
        self.idx += 1
        return self.idx

    def can_add_user(self, user_id):
        """Check if a user can add a new socket connection."""

        return self.count_for_user(user_id) < self.limit

    def add_user(self, user_id, socket) -> int:
        idx = self.gen_idx()
        self.items.append([user_id, socket, idx])
        return idx

    def count_for_user(self, user_id):
        return len(self.get_sockets_for(user_id))

    def drop_user(self, user_id, idx):
        self.items = [
            _ for _ in self.items if not ((_[0] == user_id) and (_[2] == idx))
        ]

    def get_sockets_for(self, user_id):
        return [_[1] for _ in self.items if _[0] == user_id]

    def get_sockets_for_many(self, user_ids) -> List[fastapi.WebSocket]:
        res = []
        for u in user_ids:
            res += self.get_sockets_for(u)
        return res

    async def broadcast_message_to_users(
        self, from_user_id: int, convo_id, user_ids: List[int], message: str
    ):
        """Broadcast a message to users in a conversation."""

        async def t(coros):
            with tracer.start_as_current_span("bcast_gather"):
                await asyncio.gather(*coros)

        with tracer.start_as_current_span("broadcast_message_to_users"):
            coros = []

            message_json_payload = MessageWS(
                convo_id=convo_id, content=message, originator_id=from_user_id
            ).model_dump_json()
            for websocket in self.get_sockets_for_many(user_ids):
                coros.append(websocket.send_text(message_json_payload))

            asyncio.create_task(t(coros))
