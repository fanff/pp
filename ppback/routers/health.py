import time

from fastapi import APIRouter, Depends
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from ppback.deps import get_db

router = APIRouter(tags=["health"])

_startup_time: float = time.time()


def set_startup_time(t: float) -> None:
    global _startup_time
    _startup_time = t


def get_uptime() -> float:
    return time.time() - _startup_time


@router.get("/health")
async def health(db: AsyncSession = Depends(get_db)):
    try:
        await db.execute(text("SELECT 1"))
    except Exception:
        return {"status": "error", "db": "disconnected"}, 503

    return {
        "status": "ok",
        "db": "connected",
        "uptime_seconds": round(get_uptime(), 2),
        "version": "0.1.0",
    }
