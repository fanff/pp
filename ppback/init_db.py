import asyncio

from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from ppback.db.dbfuncs import add_users, create_convo
from ppback.db.ppdb_schemas import Base


async def create_starting_point_db(session: AsyncSession):
    users = [("admin", "admin"), ("user", "user")]
    users = await add_users(session, users)

    await create_convo(session, "General", users, creator_id=users[0].id)
    await create_convo(session, "Random", users, creator_id=users[0].id)
    await create_convo(session, "About", users, creator_id=users[0].id)


async def init_db(engine: AsyncEngine):
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


if __name__ == "__main__":
    from . import main

    print("Initializing DB at " + main.DB_SESSION_STR)

    async def _run() -> None:
        await init_db(main.dbengine)
        async with main.SessionLocal() as session:
            await create_starting_point_db(session)

    asyncio.run(_run())
