import logging
import os
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from ppback.db.db_connect import to_async_db_url
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


ASYNC_DB_SESSION_STR = to_async_db_url(DB_SESSION_STR)
engine_args: dict[str, Any] = {"pool_pre_ping": True}
if not ASYNC_DB_SESSION_STR.startswith("sqlite+aiosqlite://"):
    engine_args.update({"pool_size": 10, "max_overflow": 20})

dbengine = create_async_engine(ASYNC_DB_SESSION_STR, **engine_args)
SessionLocal = async_sessionmaker(bind=dbengine, autoflush=False, expire_on_commit=False)
