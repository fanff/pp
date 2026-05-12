import asyncio
import json
import logging
import os
import time
from typing import Annotated, Any, AsyncGenerator, List

import fastapi
import jwt
from fastapi import Depends, FastAPI, HTTPException, WebSocketDisconnect
from fastapi.concurrency import asynccontextmanager
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from fastapi_cache import FastAPICache
from fastapi_cache.backends.inmemory import InMemoryBackend
from opentelemetry import trace
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import joinedload

from ppback.db.dbfuncs import (
    allusers,
    create_convo,
    get_conversation_list_for_user,
    hook_user,
    membersof,
    user_allowed_in_convo,
)
from ppback.db.ppdb_schemas import Base, Convchanges, ConvoMessage, UserInfo
from ppback.init_tracing import global_tracing_setup
from ppback.logging_config import setup_logging
from ppback.ppschema import (
    ConversationCreate,
    ConversationItem,
    ConversationList,
    MessageSchema,
    MsgInputSchema,
    MsgOutputSchema,
)
from ppback.secu.sec_utils import check_password
from ppback.wsocket import InMemSockets

# Configure logging
setup_logging()
logger = logging.getLogger("ppback")

TRACING_ENDPOINT = os.getenv("TRACING_ENDPOINT", "")
if TRACING_ENDPOINT:
    global_tracing_setup(TRACING_ENDPOINT)

tracer = trace.get_tracer(__name__)

# getting the host name of the machine
HOSTNAME = os.getenv("HOSTNAME", "localhost")

MASTER_SECRET_KEY = os.getenv("MASTER_SECRET_KEY", "mydummykey")
DB_SESSION_STR = os.getenv("DB_SESSION_STR", "sqlite:///devdb.sqlite")
CORS_ORIGIN_STR = os.getenv("CORS_ORIGIN_STR", "*")  # comma delimited list of domains
AUTO_INIT_DB = os.getenv("PPBACK_AUTO_INIT_DB", "1").lower() not in {
    "0",
    "false",
    "no",
}


def _to_async_db_url(db_url: str) -> str:
    if db_url.startswith("postgresql+asyncpg://"):
        return db_url
    if db_url.startswith("postgresql://"):
        return db_url.replace("postgresql://", "postgresql+asyncpg://", 1)
    if db_url.startswith("postgres://"):
        return db_url.replace("postgres://", "postgresql+asyncpg://", 1)
    if db_url.startswith("sqlite+aiosqlite://"):
        return db_url
    if db_url.startswith("sqlite://"):
        return db_url.replace("sqlite://", "sqlite+aiosqlite://", 1)
    return db_url


ASYNC_DB_SESSION_STR = _to_async_db_url(DB_SESSION_STR)
engine_args: dict[str, Any] = {"pool_pre_ping": True}
if not ASYNC_DB_SESSION_STR.startswith("sqlite+aiosqlite://"):
    engine_args.update({"pool_size": 10, "max_overflow": 20})

# Create a pooled async engine
dbengine = create_async_engine(ASYNC_DB_SESSION_STR, **engine_args)
SessionLocal = async_sessionmaker(bind=dbengine, autoflush=False, expire_on_commit=False)


async def initialize_database_if_needed() -> None:
    """Create and seed the development database when auto-init is enabled."""
    if not AUTO_INIT_DB:
        logger.info("Database auto-initialization disabled.")
        return

    async with dbengine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    async with SessionLocal() as session:
        user = (await session.execute(select(UserInfo).limit(1))).scalar_one_or_none()
        if user is not None:
            logger.info("user found %s", user.name)
            return

        logger.warning("Database has no users, seeding starting data now.")

        from . import init_db

        await init_db.create_starting_point_db(session)
        logger.info("Database initialized with starting data.")


@asynccontextmanager
async def lifespan(app: FastAPI):
    await initialize_database_if_needed()
    cache_backend = InMemoryBackend()
    FastAPICache.init(cache_backend, prefix="fastapi-cache")
    yield


app = FastAPI(lifespan=lifespan)

if CORS_ORIGIN_STR != "":
    origins = CORS_ORIGIN_STR.split(",")
    logger.info("Setting CORS allowed origins to %s", origins)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

# Instrument FastAPI app to automatically generate spans:
FastAPIInstrumentor.instrument_app(app)

# global object to hold open websocket connexion for user broadcast.
inmemsockets = InMemSockets()

# oauth2 with user pass in a /token endpoint.
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="token")


# Database access dependency
async def get_db() -> AsyncGenerator[AsyncSession, Any]:
    with tracer.start_as_current_span("get_session"):
        logger.debug("Getting a database session from the pool")
        session = SessionLocal()
    try:
        yield session
    finally:
        logger.debug("Closing the database session")
        await session.close()


async def decode_token(token: Annotated[str, Depends(oauth2_scheme)]) -> int:
    decoded = jwt.decode(
        token,
        key=MASTER_SECRET_KEY,
        algorithms=["HS256"],
        verify=True,
    )
    user_id = int(decoded["user_id"])
    return user_id


@app.post("/token")
async def login(
    form_data: Annotated[OAuth2PasswordRequestForm, Depends()],
    session: Annotated[AsyncSession, Depends(get_db)],
):
    logger.info("user login %s", form_data.username)
    user_info = (
        (await session.execute(select(UserInfo).where(UserInfo.name == form_data.username)))
        .scalars()
        .first()
    )
    if not user_info:
        raise HTTPException(status_code=400, detail="Incorrect username or password.")

    passcheck = check_password(form_data.password, user_info.salted_password)

    if not passcheck:
        logger.info("Password fail")
        raise HTTPException(status_code=400, detail="Incorrect username or password.")

    token = jwt.encode(
        payload={"user_id": user_info.id},
        key=MASTER_SECRET_KEY,
    )
    return {"access_token": token, "token_type": "bearer"}


@app.get("/users")
async def list_users(
    current_user_id: Annotated[int, Depends(decode_token)],
    session: Annotated[AsyncSession, Depends(get_db)],
):
    logger.info("Fetching all users for user %s", current_user_id)
    with tracer.start_as_current_span("all_users_in_db"):
        return await allusers(session)


@app.post("/conv")
async def create_conv(
    current_user_id: Annotated[int, Depends(decode_token)],
    new_conv_data: ConversationCreate,
    session: Annotated[AsyncSession, Depends(get_db)],
) -> ConversationItem:
    """Create a new conversation with the given label and members."""

    if current_user_id not in new_conv_data.members:
        new_conv_data.members.append(current_user_id)
    logger.info("adding users %s to new convo", new_conv_data.members)

    users = []
    for user_id in new_conv_data.members:
        user = await hook_user(session, user_id)
        if user is None:
            raise HTTPException(
                status_code=400,
                detail=f"User with id {user_id} does not exist.",
            )
        users.append(user)

    new_id, lab = await create_convo(session, new_conv_data.label, users)
    return ConversationItem(id=new_id, label=lab, members=new_conv_data.members)


@app.get("/conv")
async def list_conv(
    current_user_id: Annotated[int, Depends(decode_token)],
    session: Annotated[AsyncSession, Depends(get_db)],
) -> ConversationList:
    """List the conversations accessible to the user."""
    logger.info("Fetching conversations for user %s", current_user_id)
    convlist = await get_conversation_list_for_user(session, current_user_id)
    return convlist


@app.get("/conv/{conversation_id}/messages", response_model=List[MessageSchema])
async def get_messages(
    conversation_id: int,
    current_user_id: Annotated[int, Depends(decode_token)],
    session: Annotated[AsyncSession, Depends(get_db)],
    limit: int = 1000,
    after: int | None = None,
) -> List[MessageSchema]:
    """
    Retreive messages of a single conversation, optionally after a change cursor.

    """
    with tracer.start_as_current_span("privacy_check"):
        privacycheck = await user_allowed_in_convo(session, current_user_id, conversation_id)

    if privacycheck:
        with tracer.start_as_current_span("read_conv_db"):
            query = (
                select(Convchanges)
                .join(ConvoMessage, Convchanges.change_id == ConvoMessage.id)
                .where(
                    (Convchanges.conv_id == conversation_id)
                    & (Convchanges.change_type == "message")
                )
                .options(joinedload(Convchanges.convo_message))
            )
            if after is not None:
                query = query.where(Convchanges.id > after)

            results = (
                (
                    await session.execute(query.order_by(Convchanges.ts.desc()).limit(limit))
                )
                .scalars()
                .all()
            )

        with tracer.start_as_current_span("process_conv_db"):
            all_results = []
            for result in reversed(results):
                ms = MessageSchema(
                    id=result.id,
                    change_id=result.id,
                    message_id=result.convo_message.id,
                    content=result.convo_message.content,
                    sender=result.convo_message.sender_id,
                    ts=result.ts,
                )
                all_results.append(ms.model_dump())

        return all_results

    logger.warning(
        "User %s is not allowed to access conversation %s",
        current_user_id,
        conversation_id,
    )
    raise HTTPException(status_code=500, detail="error fetching conversation.")


@app.websocket("/ws")
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
            except WebSocketDisconnect:
                logger.warning("dropping user %s ", user_id)
            except RuntimeError as rerr:
                logger.warning("dropping user %s due to runtime error %s ", user_id, rerr)
            finally:
                inmemsockets.drop_user(user_id, idx)
            return

    except Exception:
        await websocket.close()
        logger.exception("uncatched error in websocket ")


@app.post("/usermsg", response_model=MsgOutputSchema)
async def new_msg(
    msg: MsgInputSchema,
    current_user_id: Annotated[int, Depends(decode_token)],
    session: Annotated[AsyncSession, Depends(get_db)],
):
    """
    Endpoint to post a new message to a conversation. This will store it & propagate it to every connected users

    Raises:
        HTTPException: If there is an issue with storing the message.
    """

    with tracer.start_as_current_span("privacy_check"):
        privacycheck = await user_allowed_in_convo(session, current_user_id, msg.conversation_id)

    if privacycheck:
        convo_id = msg.conversation_id
        with tracer.start_as_current_span("store_message_and_changes"):
            cm = ConvoMessage(content=msg.content, sender_id=current_user_id)
            session.add(cm)
            await session.flush()
            await session.refresh(cm)
            conversation_message_id = cm.id

            msg_time = time.time()
            cc = Convchanges(
                ts=msg_time,
                conv_id=convo_id,
                change_type="message",
                change_id=conversation_message_id,
            )
            session.add(cc)
            await session.flush()
            await session.refresh(cc)
            change_id = cc.id
            await session.commit()

        with tracer.start_as_current_span("find_members_of_convo"):
            members = await membersof(session, convo_id)
            usersto_send = [u["user_id"] for u in members]

        await inmemsockets.broadcast_message_to_users(
            current_user_id,
            convo_id,
            usersto_send,
            conversation_message_id,
            change_id,
            msg_time,
        )
        return {"status": "ok", "messageid": conversation_message_id, "change_id": change_id}

    raise HTTPException(400, detail="error posting message")
