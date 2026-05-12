import asyncio
import json
import logging
import os
import time
from typing import Annotated, Any, AsyncGenerator, Dict, List, Tuple

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
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, joinedload, sessionmaker

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
from ppback.ppschema import ConversationCreate, ConversationItem, ConversationList, MessageSchema, MessageWS, MsgInputSchema, MsgOutputSchema
from ppback.secu.sec_utils import check_password
from ppback.wsocket import InMemSockets

# Configure logging
setup_logging()
logger = logging.getLogger("ppback")


@asynccontextmanager
async def lifespan(app: FastAPI):
    cache_backend = InMemoryBackend()
    # Load the ML model
    FastAPICache.init(cache_backend, prefix="fastapi-cache")
    yield
    # Clean up the ML models and release the resources


app = FastAPI(lifespan=lifespan)

TRACING_ENDPOINT = os.getenv("TRACING_ENDPOINT", "")
if TRACING_ENDPOINT:
    global_tracing_setup(TRACING_ENDPOINT)

# Instrument FastAPI app to automatically generate spans:
FastAPIInstrumentor.instrument_app(app)
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

if CORS_ORIGIN_STR != "":
    origins = CORS_ORIGIN_STR.split(",")
    logger.info("Setting CORS allowed origins to %s", origins)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=origins,  # List of origins
        allow_credentials=True,
        allow_methods=["*"],  # Allow all methods
        allow_headers=["*"],  # Allow all headers
    )


# global object to hold open websocket connexion for user broadcast.
inmemsockets = InMemSockets()

# oauth2 with user pass in a /token endpoint.
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="token")

# Create a pooled engine
dbengine = create_engine(DB_SESSION_STR, pool_size=10, max_overflow=20)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=dbengine)

def initialize_database_if_needed() -> None:
    """Create and seed the development database when auto-init is enabled."""
    if not AUTO_INIT_DB:
        logger.info("Database auto-initialization disabled.")
        return

    session = SessionLocal()
    try:
        try:
            user: UserInfo | None = session.query(UserInfo).first()
            if user is not None:
                logger.info("user found %s", user.name)
                return
        except Exception:
            logger.warning("Database schema not initialized, creating tables now.")
            Base.metadata.create_all(bind=dbengine)
        else:
            logger.warning("Database has no users, seeding starting data now.")

        from . import init_db

        init_db.create_starting_point_db(session)
        logger.info("Database initialized with starting data.")
    finally:
        session.close()


initialize_database_if_needed()


# Database access dependency
async def get_db() -> AsyncGenerator[Session, Any]:
    with tracer.start_as_current_span("get_session"):
        logger.debug("Getting a database session from the pool")
        session = SessionLocal()
    try:
        yield session
    finally:
        logger.debug("Closing the database session")
        session.close()


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
    session: Annotated[Session ,Depends(get_db)],
):
    logger.info("user login %s", form_data.username)
    # find user information in db
    user_info = (
        session.query(UserInfo).filter(UserInfo.name == form_data.username).first()
    )
    if not user_info:
        raise HTTPException(status_code=400, detail="Incorrect username or password.")

    passcheck = check_password(form_data.password, user_info.salted_password)

    if not passcheck:
        logger.info("Password fail")
        raise HTTPException(status_code=400, detail="Incorrect username or password.")
    # should improve with a signature or something
    token = jwt.encode(
        payload={"user_id": user_info.id},
        key=MASTER_SECRET_KEY,
    )
    return {"access_token": token, "token_type": "bearer"}


@app.get("/users")
async def list_users(
    current_user_id: Annotated[int, Depends(decode_token)],
):
    logger.info("Fetching all users for user %s", current_user_id)
    with tracer.start_as_current_span("all_users_in_db"):
        return await allusers(get_db)

@app.post("/conv")
async def create_conv(current_user_id: Annotated[int, Depends(decode_token)], 
                      new_conv_data: ConversationCreate) -> ConversationItem:
    """Create a new conversation with the given label and members."""
    session: Session = await anext(get_db())

    # check if the user is trying to add himself in the conversation, if not add him.
    if current_user_id not in new_conv_data.members:
        new_conv_data.members.append(current_user_id)
    logger.info("adding users %s to new convo",new_conv_data.members )
    # get the user objects for the members
    users = []
    for user_id in new_conv_data.members:
        user = await hook_user(session, user_id)
        if user is None:
            raise HTTPException(status_code=400, detail=f"User with id {user_id} does not exist.")
        if not isinstance(user, UserInfo):
            user = UserInfo.from_dict(
                user
            )  # in case the cache return a dict instead of an object
        users.append(user)
    
    # create the conversation
    new_id, lab = create_convo(session, new_conv_data.label, users)
    return ConversationItem(id=new_id, label=lab, members=new_conv_data.members)


@app.get("/conv")
async def list_conv(
    current_user_id: Annotated[int, Depends(decode_token)],
) -> ConversationList:
    """List the conversations accessible to the user."""
    logger.info("Fetching conversations for user %s", current_user_id)
    convlist = await get_conversation_list_for_user(get_db, current_user_id)
    return convlist

@app.get("/conv/{conversation_id}/messages", response_model=List[MessageSchema])
async def get_messages(
    conversation_id: int,
    current_user_id: Annotated[int, Depends(decode_token)],
    limit: int = 1000,
) -> List[MessageSchema]:
    """
    Retreive all last messages of a single conversation. Sorted by timestamp

    """
    with tracer.start_as_current_span("privacy_check"):
        privacycheck = await user_allowed_in_convo(
            get_db, current_user_id, conversation_id
        )

    if privacycheck:
        session: Session = await anext(get_db())
        with tracer.start_as_current_span("read_conv_db"):
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

        with tracer.start_as_current_span("process_conv_db"):
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
        logger.warning("User %s is not allowed to access conversation %s", current_user_id, conversation_id)
        raise HTTPException(status_code=500, detail="error fetching conversation.")


@app.websocket("/ws")
async def websocket_endpoint(websocket: fastapi.WebSocket):

    # this method bellow is checking the "Authorization" in the websocket header connection packet.
    # This is not always working with every clients. (Godot engine client complained in web mode).
    # This SHOULD be the way to go; I don't want to accept the webscoekt connection if the user is not legitimate.
    # But Godot...
    # try:
    #     token = websocket.headers.get("Authorization")
    #     token = token.split(" ")[1]
    #     session = await anext(get_db())
    #     user = decode_token(token,session)
    # except Exception as e:
    #     await websocket.close()
    #     raise e

    # accept the connection
    await websocket.accept()

    logger.info("accepting websocket connection from %s", websocket.client)

    try:
        # wait for the first packet. Since I accept anyone this is a DOS target...
        # to "escape" I give 5 seconds to the user to send me the "special auth packet" with the api token.
        try:
            data = await asyncio.wait_for(websocket.receive(), timeout=5)
        except asyncio.TimeoutError:
            # no packet ?!  bye bye
            logger.warning("no data received in time, closing websocket connection from %s", websocket.client)

            await websocket.close()
            return

        logger.info(
            "got data , %s", data
        )  # not logging data, because it contains the secure token of the user
        pld = json.loads(data["text"])["token"]
        token = pld

        logger.info("got token %s ", token)
        session = await anext(get_db())
        user_id = await decode_token(token)  # this raise exception if failed
        user = await hook_user(session, user_id)  # this raise exception if failed
        if not isinstance(user, UserInfo):
            user = UserInfo.from_dict(
                user
            )  # in case the cache return a dict instead of an object
        user_name = user.name
        logger.info("got user %s ", user_name)
        if not inmemsockets.can_add_user(user_id):
            await websocket.close()

        idx = inmemsockets.add_user(user_id, websocket)

        keep_user_connected = True
        while keep_user_connected:
            try:
                data = await websocket.receive_text()
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
        # await websocket.send_text(f"Message text was: {data}")


@app.post("/usermsg", response_model=MsgOutputSchema)
async def new_msg(
    msg: MsgInputSchema,
    current_user_id: Annotated[int, Depends(decode_token)],
):
    """
    Endpoint to post a new message to a conversation. This will store it & propagate it to every connected users

    Raises:
        HTTPException: If there is an issue with storing the message.
    """

    with tracer.start_as_current_span("privacy_check"):
        privacycheck = await user_allowed_in_convo(
            get_db, current_user_id, msg.conversation_id
        )

    if privacycheck:
        convo_id = msg.conversation_id
        session: Session = await anext(get_db())
        with tracer.start_as_current_span("store_message_and_changes"):
            # Add the first object
            cm = ConvoMessage(content=msg.content, sender_id=current_user_id)
            session.add(cm)
            session.flush()
            session.refresh(cm)
            conversation_message_id = cm.id
            # Use the ID of the first object for the second object
            msg_time = time.time()
            cc = Convchanges(
                ts=msg_time,
                conv_id=convo_id,
                change_type="message",
                change_id=conversation_message_id,
            )
            session.add(cc)
            # Commit both objects in a single transaction
            session.commit()

        with tracer.start_as_current_span("find_members_of_convo"):
            members = await membersof(session, convo_id)
            usersto_send = [u["user_id"] for u in members]

        
        await inmemsockets.broadcast_message_to_users(
            current_user_id, convo_id, usersto_send, conversation_message_id ,
             msg_time,
              msg.content
        )
        return {"status": "ok", "messageid": conversation_message_id}

    raise HTTPException(400, detail="error posting message")
