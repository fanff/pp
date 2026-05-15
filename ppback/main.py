import logging
import time
import uuid
import contextvars
from typing import Annotated

from fastapi import Depends, FastAPI
from fastapi.concurrency import asynccontextmanager
from fastapi.middleware.cors import CORSMiddleware
from fastapi_cache import FastAPICache
from fastapi_cache.backends.inmemory import InMemoryBackend
from opentelemetry import trace
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from sqlalchemy import select
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request

from ppback.config import AUTO_INIT_DB, CORS_ORIGIN_STR, TRACING_ENDPOINT, SessionLocal, dbengine
from ppback.db.ppdb_schemas import Base, UserInfo
from ppback.deps import decode_token  # noqa: F401
from ppback.init_tracing import global_tracing_setup
from ppback.middleware.metrics import metrics_router, MetricsMiddleware
from ppback.routers import admin, health, messaging, users, ws
from ppback.routers.health import set_startup_time

logger = logging.getLogger("ppback")

tracer = trace.get_tracer(__name__)

_request_id_ctx: contextvars.ContextVar[str] = contextvars.ContextVar("request_id", default="")


def get_request_id() -> str:
    return _request_id_ctx.get()


class RequestIDMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        req_id = request.headers.get("X-Request-ID", str(uuid.uuid4()))
        token = _request_id_ctx.set(req_id)
        try:
            response = await call_next(request)
            response.headers["X-Request-ID"] = req_id
            return response
        finally:
            _request_id_ctx.reset(token)


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
    import time as _time
    set_startup_time(_time.time())
    if TRACING_ENDPOINT:
        global_tracing_setup(TRACING_ENDPOINT)
        FastAPIInstrumentor.instrument_app(app)
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

app.add_middleware(RequestIDMiddleware)
app.add_middleware(MetricsMiddleware)

app.include_router(metrics_router)
app.include_router(admin.router)
app.include_router(health.router)
app.include_router(users.router)
app.include_router(messaging.router)
app.include_router(ws.router)
