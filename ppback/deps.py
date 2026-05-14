import logging
from typing import Annotated, AsyncGenerator, Any

import jwt
from fastapi import Depends
from fastapi.security import OAuth2PasswordBearer
from opentelemetry import trace
from sqlalchemy.ext.asyncio import AsyncSession

from fastapi import HTTPException
from sqlalchemy import select

from ppback.config import MASTER_SECRET_KEY, SessionLocal
from ppback.db.ppdb_schemas import UserInfo

logger = logging.getLogger("ppback")
tracer = trace.get_tracer(__name__)

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="token")


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


async def require_admin(
    current_user_id: Annotated[int, Depends(decode_token)],
    session: Annotated[AsyncSession, Depends(get_db)],
) -> int:
    user = await session.get(UserInfo, current_user_id)
    if not user or not user.is_admin:
        raise HTTPException(status_code=403, detail="Admin privileges required")
    return current_user_id
