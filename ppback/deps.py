import logging
from typing import Annotated, AsyncGenerator, Any

import jwt
from fastapi import Depends
from fastapi.security import OAuth2PasswordBearer
from opentelemetry import trace
from sqlalchemy.ext.asyncio import AsyncSession

from ppback.config import MASTER_SECRET_KEY, SessionLocal

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
