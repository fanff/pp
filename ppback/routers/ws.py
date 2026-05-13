import asyncio
import json
import logging

import fastapi
from fastapi import APIRouter
from opentelemetry import trace

from ppback.config import SessionLocal
from ppback.db.dbfuncs import hook_user
from ppback.deps import decode_token
from ppback.wsocket import inmemsockets

logger = logging.getLogger("ppback")
tracer = trace.get_tracer(__name__)

router = APIRouter()


@router.websocket("/ws")
async def websocket_endpoint(websocket: fastapi.WebSocket):
    await websocket.accept()
    logger.info("accepting websocket connection from %s", websocket.client)

    try:
        try:
            data = await asyncio.wait_for(websocket.receive(), timeout=5)
        except asyncio.TimeoutError:
            logger.warning(
                "no data received in time, closing websocket connection from %s",
                websocket.client,
            )
            await websocket.close()
            return

        logger.info("got websocket auth packet from %s", websocket.client)
        pld = json.loads(data["text"])["token"]
        token = pld

        logger.info("got websocket auth token from %s", websocket.client)
        user_id = await decode_token(token)
        async with SessionLocal() as session:
            user = await hook_user(session, user_id)
        if user is None:
            raise ValueError("websocket token references an unknown user")
        user_name = user.name
        logger.info("websocket authenticated user %s", user_name)
        if not inmemsockets.can_add_user(user_id):
            await websocket.close()
            return

        idx = inmemsockets.add_user(user_id, websocket)

        keep_user_connected = True
        while keep_user_connected:
            try:
                await websocket.receive_text()
            except fastapi.WebSocketDisconnect:
                logger.warning("dropping user %s ", user_id)
            except RuntimeError as rerr:
                logger.warning("dropping user %s due to runtime error %s ", user_id, rerr)
            finally:
                inmemsockets.drop_user(user_id, idx)
            return

    except Exception:
        await websocket.close()
        logger.exception("uncatched error in websocket ")
