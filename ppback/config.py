import logging
import os
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from ppback.logging_config import setup_logging

setup_logging()
logger = logging.getLogger("ppback")

TRACING_ENDPOINT = os.getenv("TRACING_ENDPOINT", "")
HOSTNAME = os.getenv("HOSTNAME", "localhost")
MASTER_SECRET_KEY = os.getenv("MASTER_SECRET_KEY", "mydummykey")
DB_SESSION_STR = os.getenv("DB_SESSION_STR", "sqlite:///devdb.sqlite")
CORS_ORIGIN_STR = os.getenv("CORS_ORIGIN_STR", "*")
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

dbengine = create_async_engine(ASYNC_DB_SESSION_STR, **engine_args)
SessionLocal = async_sessionmaker(bind=dbengine, autoflush=False, expire_on_commit=False)
