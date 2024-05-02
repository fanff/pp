import asyncio
import json
import logging
import os
import time
from typing import Annotated, List, Tuple

import fastapi
import jwt
from fastapi import Depends, HTTPException, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from sqlalchemy.orm import Session, joinedload

from ppback.db.db_connect import get_session
from ppback.db.ppdb_schemas import (
    Conv,
    Convchanges,
    ConvoMessage,
    ConvPrivacyMembers,
    UserInfo,
)
from ppback.ppschema import MessageSchema, MessageWS, MsgInputSchema, MsgOutputSchema
from ppback.secu.sec_utils import check_password


class InMemSockets:
    """Keeping sockets open, in a global memory object."""

    def __init__(self):
        self.items: List[Tuple[int, fastapi.WebSocket, int]] = []
        self.limit = 5
        self.idx = 0

    def gen_idx(self):
        self.idx += 1
        return self.idx

    def can_add_user(self, user_id):
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


logger = logging.getLogger("ppback")
app = fastapi.FastAPI()


MASTER_SECRET_KEY = os.getenv("MASTER_SECRET_KEY", "mydumykey")
DB_SESSION_STR = os.getenv("DB_SESSION_STR", "sqlite:///devdb/chat_database.db")
CORS_ORIGIN_STR = os.getenv("CORS_ORIGIN_STR", "")  # comma delimited list of domains

if CORS_ORIGIN_STR:
    origins = json.loads(CORS_ORIGIN_STR)

    app.add_middleware(
        CORSMiddleware,
        allow_origins=origins,  # List of origins
        allow_credentials=True,
        allow_methods=["*"],  # Allow all methods
        allow_headers=["*"],  # Allow all headers
    )


# global object to hold open websocket connexion for user broadcast.
inmemsockets = InMemSockets()


# Database access dependency
async def get_db():
    db = get_session(DB_SESSION_STR)()
    try:
        yield db
    finally:
        db.close()


# oauth2 with user pass in a /token endpoint.
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="token")


async def get_current_user(
    token: Annotated[str, Depends(oauth2_scheme)], session: Session = Depends(get_db)
):
    """user validation dependency; to be used in all Endpoint."""
    # to improve : use some cache here to save a database call
    user = decode_token(token, session)
    return user


def decode_token(token, session) -> UserInfo:
    decoded = jwt.decode(
        token,
        key=MASTER_SECRET_KEY,
        algorithms=[
            "HS256",
        ],
    )
    return session.query(UserInfo).filter(UserInfo.id == decoded["user_id"]).first()


@app.post("/token")
async def login(
    form_data: Annotated[OAuth2PasswordRequestForm, Depends()],
    session: Session = Depends(get_db),
):

    # find user information in sqlite
    user_info = (
        session.query(UserInfo).filter(UserInfo.name == form_data.username).first()
    )
    if not user_info:
        raise HTTPException(status_code=400, detail="Incorrect username or password.")

    passcheck = check_password(form_data.password, user_info.salted_password)

    if not passcheck:
        raise HTTPException(status_code=400, detail="Incorrect username or password.")

    # should improve with a signature or something
    token = jwt.encode(
        payload={"user_id": user_info.id},
        key=MASTER_SECRET_KEY,
    )
    return {"access_token": token, "token_type": "bearer"}


@app.get("/conv")
async def list_conv(
    current_user: Annotated[UserInfo, Depends(get_current_user)],
    session: Session = Depends(get_db),
):
    """list the conversations"""

    q = session.query(ConvPrivacyMembers).filter(
        ConvPrivacyMembers.user_id == current_user.id
    )
    all_convids = [v.conv_id for v in q.all()]
    all_convs = session.query(Conv).filter(Conv.id.in_(all_convids)).all()

    return [{"id": _.id, "label": _.label} for _ in all_convs]


@app.get("/users")
async def list_conv(
    current_user: Annotated[UserInfo, Depends(get_current_user)],
    session: Session = Depends(get_db),
):
    allu = session.query(UserInfo).all()
    return [{"id": u.id, "name": u.name, "nickname": u.nickname} for u in allu]


@app.get("/conv/{conversation_id}")
async def getconv(
    conversation_id: int,
    user: Annotated[UserInfo, Depends(get_current_user)],
    session: Session = Depends(get_db),
    limit: int = 1000,
) -> List[MessageSchema]:
    """
    Retreive all last messages of a single conversation. Sorted by timestamp

    """
    privacycheck = (
        session.query(ConvPrivacyMembers)
        .filter(
            (ConvPrivacyMembers.user_id == user.id)
            & (ConvPrivacyMembers.conv_id == conversation_id)
        )
        .count()
    )

    if privacycheck == 1:
        results = (
            session.query(Convchanges)
            .join(ConvoMessage, Convchanges.change_id == ConvoMessage.id)
            .filter(
                (Convchanges.conv_id == conversation_id)
                & (Convchanges.change_type == "message")
            )
            .options(joinedload(Convchanges.convo_message))
            .order_by(Convchanges.ts.desc())
            .limit(limit)
            .all()
        )
        all_results = []
        for result in reversed(results):
            ms = MessageSchema(
                id=result.id,
                content=result.convo_message.content,
                sender=result.convo_message.sender_id,
                ts=result.ts,
            )
            all_results.append(ms.model_dump())

        return all_results
    else:
        raise HTTPException(status_code=500, detail="error fetching conversation.")


@app.websocket("/ws")
async def websocket_endpoint(websocket: fastapi.WebSocket):

    # this method bellow is checking the "Authorization" in the websocket header connection packet.
    # This is not always working with every clients. (Godot engine client complained in web mode).
    # This SHOULD be the way to go; I don't want to accept the webscoekt connection if the user is not legitimate.
    # But Godot.. <3.
    # try:
    #     token = websocket.headers.get("Authorization")
    #     token = token.split(" ")[1]
    #     session = await anext(get_db())
    #     user = decode_token(token,session)
    # except Exception as e:
    #     await websocket.close()
    #     raise e

    ## check the token before accepting the websocket
    # token = websocket.headers.get("Authorization")
    ## if token is not valid, reject the websocket
    # if not token:
    #    await websocket.close()
    #    return
    #

    # accept the connection
    await websocket.accept()

    logger.info("accepting websocket ")

    try:
        # wait for the first packet. Since I accept anyone this is a DOS target...
        # to "escape" I give 5 seconds to the user to send me the "special auth packet" with the api token.
        try:
            data = await asyncio.wait_for(websocket.receive(), timeout=5)
        except asyncio.TimeoutError:
            # no packet ?!  bye bye
            await websocket.close()
            return

        logger.info(
            "got data , %s", len(data)
        )  # not logging data, because it contains the secure token of the user
        pld = json.loads(data["bytes"])
        token = pld[1].split(" ")[-1]
        session = await anext(get_db())
        user = decode_token(token, session)  # this raise exception if failed

        logger.warning("got user %s ", user)
        if not inmemsockets.can_add_user(user.id):
            await websocket.close()

        idx = inmemsockets.add_user(user.id, websocket)

        keep_user_connected = True
        while keep_user_connected:
            try:
                data = await websocket.receive_text()
            except WebSocketDisconnect:
                logger.warning("dropping user %s ", user.id)
            finally:
                inmemsockets.drop_user(user.id, idx)

            return

    except Exception:
        await websocket.close()
        logger.exception("uncatched error in websocket ")
        # await websocket.send_text(f"Message text was: {data}")


async def broadcast_message_to_users(
    from_user: UserInfo, convo_id, user_ids: List[int], message: str
):
    coros = []

    for websocket in inmemsockets.get_sockets_for_many(user_ids):
        m = MessageWS(convo_id=convo_id, content=message, originator=from_user.id)
        coros.append(websocket.send_text(m.model_dump_json()))

    all_res = await asyncio.gather(*coros)


@app.post("/usermsg", response_model=MsgOutputSchema)
async def new_msg(
    msg: MsgInputSchema,
    user: Annotated[UserInfo, Depends(get_current_user)],
    session: Session = Depends(get_db),
):
    """
    Endpoint to post a new message to a conversation. This will store it & propagate it to every connected users

    Raises:
        HTTPException: If there is an issue with storing the message.
    """
    new_content = msg.content

    privacycheck = (
        session.query(ConvPrivacyMembers)
        .filter(
            (ConvPrivacyMembers.user_id == user.id)
            & (ConvPrivacyMembers.conv_id == msg.conversation_id)
        )
        .count()
    )

    if privacycheck:
        convo = session.query(Conv).filter(Conv.id == msg.conversation_id).first()
        cm = ConvoMessage(content=new_content, sender_id=user.id)
        session.add(cm)
        session.commit()
        cc = Convchanges(
            ts=time.time(), conv_id=convo.id, change_type="message", change_id=cm.id
        )

        session.add(cc)
        session.commit()

        members = (
            session.query(ConvPrivacyMembers)
            .filter((ConvPrivacyMembers.conv_id == msg.conversation_id))
            .all()
        )
        usersto_send = [u.user_id for u in members]

        await broadcast_message_to_users(user, convo.id, usersto_send, new_content)
        return {"status": "ok"}

    raise HTTPException(400, detail="error posting message")
