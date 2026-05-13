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
        self.items: List[Tuple[int, fastapi.WebSocket, int]] = []
        self.limit = limit
        self.idx = 0

    def gen_idx(self):
        self.idx += 1
        return self.idx

    def can_add_user(self, user_id):
        return self.count_for_user(user_id) < self.limit

    def add_user(self, user_id, socket) -> int:
        idx = self.gen_idx()
        self.items.append((user_id, socket, idx))
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
        self,
        from_user_id: int,
        convo_id,
        user_ids: List[int],
        msg_id: int,
        ts: float,
    ):
        async def _safe_send(websocket: fastapi.WebSocket, payload: str) -> None:
            try:
                await asyncio.wait_for(websocket.send_text(payload), timeout=1)
            except Exception:
                logger.debug("websocket broadcast send failed", exc_info=True)

        with tracer.start_as_current_span("broadcast_message_to_users"):
            coros = []

            message_json_payload = MessageWS(
                conversation_id=convo_id,
                message_id=msg_id,
                sender_id=from_user_id,
                ts=ts,
            ).model_dump_json()
            for websocket in self.get_sockets_for_many(user_ids):
                coros.append(_safe_send(websocket, message_json_payload))

            if coros:
                with tracer.start_as_current_span("bcast_gather"):
                    await asyncio.gather(*coros, return_exceptions=True)


inmemsockets = InMemSockets()
