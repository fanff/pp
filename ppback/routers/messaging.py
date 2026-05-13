import logging
import time
from typing import Annotated, List

from fastapi import APIRouter, Depends, HTTPException
from opentelemetry import trace
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload

from ppback.db.dbfuncs import (
    create_convo,
    get_conversation_list_for_user,
    hook_user,
    membersof,
    user_allowed_in_convo,
)
from ppback.db.ppdb_schemas import Convchanges, ConvoMessage
from ppback.deps import decode_token, get_db
from ppback.ppschema import (
    ConversationCreate,
    ConversationItem,
    ConversationList,
    MessageSchema,
    MsgInputSchema,
    MsgOutputSchema,
)
from ppback.wsocket import inmemsockets

logger = logging.getLogger("ppback")
tracer = trace.get_tracer(__name__)

router = APIRouter()


@router.post("/conv")
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


@router.get("/conv")
async def list_conv(
    current_user_id: Annotated[int, Depends(decode_token)],
    session: Annotated[AsyncSession, Depends(get_db)],
) -> ConversationList:
    """List the conversations accessible to the user."""
    logger.info("Fetching conversations for user %s", current_user_id)
    convlist = await get_conversation_list_for_user(session, current_user_id)
    return convlist


@router.get("/conv/{conversation_id}/messages", response_model=List[MessageSchema])
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
            all_results: list[MessageSchema] = []
            for result in reversed(results):
                message = result.convo_message
                if message is None:
                    logger.warning(
                        "conversation change %s has no associated message", result.id
                    )
                    continue

                ms = MessageSchema(
                    id=result.id,
                    change_id=result.id,
                    message_id=message.id,
                    content=message.content,
                    sender=message.sender_id,
                    ts=result.ts,
                )
                all_results.append(ms)

        return all_results

    logger.warning(
        "User %s is not allowed to access conversation %s",
        current_user_id,
        conversation_id,
    )
    raise HTTPException(status_code=500, detail="error fetching conversation.")


@router.post("/usermsg", response_model=MsgOutputSchema)
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
