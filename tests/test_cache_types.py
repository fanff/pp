import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from ppback.db.dbfuncs import get_conversation_list_for_user, hook_user
from ppback.db.ppdb_schemas import UserInfo
from ppback.main import DB_SESSION_STR, get_db
from ppback.ppschema import ConversationList


@pytest.mark.asyncio
async def test_hook_user_returns_typed_user_with_warm_cache(client):
    _client, _tokens = client
    engine_test = create_engine(DB_SESSION_STR, connect_args={"check_same_thread": False})
    SessionLocalTest = sessionmaker(autocommit=False, autoflush=False, bind=engine_test)
    db = SessionLocalTest()

    try:
        first = await hook_user(db, 1)
        second = await hook_user(db, 1)
    finally:
        db.close()

    assert isinstance(first, UserInfo)
    assert isinstance(second, UserInfo)
    assert first.id == second.id == 1


@pytest.mark.asyncio
async def test_get_conversation_list_returns_typed_model_with_warm_cache(client):
    _client, _tokens = client

    first = await get_conversation_list_for_user(get_db, 1)
    second = await get_conversation_list_for_user(get_db, 1)

    assert isinstance(first, ConversationList)
    assert isinstance(second, ConversationList)
    assert len(second.conversations) >= 1
