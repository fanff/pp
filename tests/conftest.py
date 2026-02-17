

import os
import time
from ppback.db.ppdb_schemas import Base, UserInfo
import pytest
from fastapi.testclient import TestClient
from ppback.main import DB_SESSION_STR, app  # Your FastAPI app
from ppback.db.dbfuncs import add_users, create_convo
from fastapi_cache import FastAPICache
from fastapi_cache.backends.inmemory import InMemoryBackend
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker



@pytest.fixture()
def client():
    # Connect to the database engine directly from your app configuration
    # In this case, it's using the SQLite database (you could modify for any other db)
    engine_test = create_engine(DB_SESSION_STR, connect_args={"check_same_thread": False})

    # Ensure that tables are created for the test
    Base.metadata.create_all(bind=engine_test)
    # Create a session using your app's sessionmaker (SessionLocal is assumed from app config)
    # We won’t be managing the session directly; the app will use it.
    SessionLocalTest = sessionmaker(autocommit=False, autoflush=False, bind=engine_test)
    db = SessionLocalTest()

    # create a test users and conversations
    user_alice = add_users(db, [["alice", "testpassword"]])[0]
    user_bob = add_users(db, [["bob", "testpassword"]])[0]
    user_charlie = add_users(db, [["charlie", "testpassword"]])[0]

    create_convo(db, "general", [user_alice.id, user_bob.id, user_charlie.id])
    create_convo(db, "a_and_b", [user_alice.id, user_bob.id])
    db.close()

    client = TestClient(app)
    cache_backend = InMemoryBackend()
    FastAPICache.init(cache_backend, prefix="fastapi-cache")
    alice_token = client.post("/token", data={"username": "alice", 
                                "password": "testpassword",
                                "grant_type":"password"},
                                headers={"Content-Type": "application/x-www-form-urlencoded"}
                                ).json()["access_token"]

    bob_token = client.post("/token", data={"username": "bob", 
                                "password": "testpassword",
                                "grant_type":"password"},
                                headers={"Content-Type": "application/x-www-form-urlencoded"}
                                ).json()["access_token"]

    charlie_token = client.post("/token", data={"username": "charlie", 
                                "password": "testpassword",
                                "grant_type":"password"},
                                headers={"Content-Type": "application/x-www-form-urlencoded"}
                                ).json()["access_token"]



    yield client,(alice_token,bob_token,charlie_token)
    # Teardown: close the client after tests
    client.close()

    # Teardown: drop the tables after tests
    Base.metadata.drop_all(bind=engine_test)
