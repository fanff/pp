import logging
from typing import Annotated

import jwt
from fastapi import APIRouter, Depends, HTTPException
from fastapi.security import OAuth2PasswordRequestForm
from opentelemetry import trace
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ppback.config import MASTER_SECRET_KEY
from ppback.db.dbfuncs import allusers
from ppback.db.ppdb_schemas import UserInfo
from ppback.deps import decode_token, get_db
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


@router.get("/users")
async def list_users(
    current_user_id: Annotated[int, Depends(decode_token)],
    session: Annotated[AsyncSession, Depends(get_db)],
):
    logger.info("Fetching all users for user %s", current_user_id)
    with tracer.start_as_current_span("all_users_in_db"):
        return await allusers(session)
