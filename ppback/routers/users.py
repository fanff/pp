import logging
from typing import Annotated

import jwt
from fastapi import APIRouter, Depends, HTTPException
from fastapi.security import OAuth2PasswordRequestForm
from opentelemetry import trace
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ppback.config import MASTER_SECRET_KEY
from ppback.db.dbfuncs import (
    accept_friend_request,
    create_invite_code,
    get_friend_requests,
    get_friends,
    get_visible_users,
    reject_friend_request,
    submit_invite_code,
)
from ppback.db.ppdb_schemas import UserInfo
from ppback.deps import decode_token, get_db
from ppback.ppschema import (
    FriendRequestOut,
    FriendRequestSubmit,
    FriendshipOut,
    InviteCodeOut,
)
from ppback.secu.sec_utils import check_password

logger = logging.getLogger("ppback")
tracer = trace.get_tracer(__name__)

router = APIRouter()


@router.post("/token")
async def login(
    form_data: Annotated[OAuth2PasswordRequestForm, Depends()],
    session: Annotated[AsyncSession, Depends(get_db)],
):
    logger.info("user login %s", form_data.username)
    user_info = (
        (
            await session.execute(
                select(UserInfo).where(UserInfo.name == form_data.username)
            )
        )
        .scalars()
        .first()
    )
    if not user_info:
        raise HTTPException(
            status_code=400, detail="Incorrect username or password."
        )

    passcheck = check_password(form_data.password, user_info.salted_password)

    if not passcheck:
        logger.info("Password fail")
        raise HTTPException(
            status_code=400, detail="Incorrect username or password."
        )

    token = jwt.encode(
        payload={"user_id": user_info.id},
        key=MASTER_SECRET_KEY,
    )
    return {"access_token": token, "token_type": "bearer"}


@router.get("/users")
async def list_users(
    current_user_id: Annotated[int, Depends(decode_token)],
    session: Annotated[AsyncSession, Depends(get_db)],
):
    logger.info("Fetching visible users for user %s", current_user_id)
    with tracer.start_as_current_span("visible_users_db"):
        return await get_visible_users(session, current_user_id)


@router.post("/invite-codes", response_model=InviteCodeOut)
async def create_invite(
    current_user_id: Annotated[int, Depends(decode_token)],
    session: Annotated[AsyncSession, Depends(get_db)],
):
    ic = await create_invite_code(session, current_user_id)
    return {"code": ic.code}


@router.post("/friend-requests", response_model=FriendRequestOut)
async def submit_invite(
    body: FriendRequestSubmit,
    current_user_id: Annotated[int, Depends(decode_token)],
    session: Annotated[AsyncSession, Depends(get_db)],
):
    try:
        fr = await submit_invite_code(session, body.invite_code, current_user_id)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return {
        "id": fr.id,
        "from_user_id": fr.from_user_id,
        "to_user_id": fr.to_user_id,
        "status": fr.status,
    }


@router.get("/friend-requests", response_model=list[FriendRequestOut])
async def list_friend_requests(
    current_user_id: Annotated[int, Depends(decode_token)],
    session: Annotated[AsyncSession, Depends(get_db)],
):
    return await get_friend_requests(session, current_user_id)


@router.post("/friend-requests/{request_id}/accept", response_model=FriendshipOut)
async def accept_request(
    request_id: int,
    current_user_id: Annotated[int, Depends(decode_token)],
    session: Annotated[AsyncSession, Depends(get_db)],
):
    try:
        fs = await accept_friend_request(session, request_id, current_user_id)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    from ppback.db.dbfuncs import hook_user

    friend_id = (
        fs.user_b_id if fs.user_a_id == current_user_id else fs.user_a_id
    )
    friend = await hook_user(session, friend_id)
    return {
        "user_id": friend_id,
        "name": friend.name if friend else "unknown",
        "nickname": friend.nickname if friend else "unknown",
        "since": fs.created_at,
    }


@router.post("/friend-requests/{request_id}/reject")
async def reject_request(
    request_id: int,
    current_user_id: Annotated[int, Depends(decode_token)],
    session: Annotated[AsyncSession, Depends(get_db)],
):
    try:
        await reject_friend_request(session, request_id, current_user_id)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return {"status": "rejected"}


@router.get("/friends", response_model=list[FriendshipOut])
async def list_friends(
    current_user_id: Annotated[int, Depends(decode_token)],
    session: Annotated[AsyncSession, Depends(get_db)],
):
    return await get_friends(session, current_user_id)
