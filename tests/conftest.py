import asyncio
import os

os.environ["DB_SESSION_STR"] = "sqlite:////tmp/pp-test.sqlite"
os.environ["PPBACK_AUTO_INIT_DB"] = "0"

from ppback.db.ppdb_schemas import Base, UserInfo
import pytest
from fastapi.testclient import TestClient
from ppback.main import SessionLocal, app, dbengine
from ppback.db.dbfuncs import add_users, create_convo
from fastapi_cache import FastAPICache
from fastapi_cache.backends.inmemory import InMemoryBackend



@pytest.fixture()
def client():
    async def setup_db() -> None:
        async with dbengine.begin() as conn:
            await conn.run_sync(Base.metadata.drop_all)
            await conn.run_sync(Base.metadata.create_all)

        async with SessionLocal() as db:
            user_alice = (await add_users(db, [["alice", "testpassword"]]))[0]
            user_bob = (await add_users(db, [["bob", "testpassword"]]))[0]
            user_charlie = (await add_users(db, [["charlie", "testpassword"]]))[0]

            await create_convo(db, "general", [user_alice, user_bob, user_charlie])
            await create_convo(db, "a_and_b", [user_alice, user_bob])

    async def teardown_db() -> None:
        async with dbengine.begin() as conn:
            await conn.run_sync(Base.metadata.drop_all)

    asyncio.run(setup_db())

    cache_backend = InMemoryBackend()
    FastAPICache.reset()
    FastAPICache.init(cache_backend, prefix="fastapi-cache")

    client = TestClient(app)
    try:
        alice_token = client.post(
            "/token",
            data={"username": "alice", "password": "testpassword", "grant_type": "password"},
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        ).json()["access_token"]

        bob_token = client.post(
            "/token",
            data={"username": "bob", "password": "testpassword", "grant_type": "password"},
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        ).json()["access_token"]

        charlie_token = client.post(
            "/token",
            data={"username": "charlie", "password": "testpassword", "grant_type": "password"},
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        ).json()["access_token"]

        yield client, (alice_token, bob_token, charlie_token)
    finally:
        client.close()
        FastAPICache.reset()
        cache_backend._store.clear()
        asyncio.run(teardown_db())
