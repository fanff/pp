import pytest

from ppback.db.dbfuncs import get_conversation_list_for_user, hook_user
from ppback.db.ppdb_schemas import UserInfo
from ppback.main import SessionLocal
from ppback.ppschema import ConversationList


@pytest.mark.asyncio
async def test_hook_user_returns_typed_user_with_warm_cache(client):
    _client, _tokens = client

    async with SessionLocal() as db:
        first = await hook_user(db, 1)
        second = await hook_user(db, 1)

    assert isinstance(first, UserInfo)
    assert isinstance(second, UserInfo)
    assert first.id == second.id == 1


@pytest.mark.asyncio
async def test_get_conversation_list_returns_typed_model_with_warm_cache(client):
    _client, _tokens = client

    async with SessionLocal() as db:
        first = await get_conversation_list_for_user(db, 1)
        second = await get_conversation_list_for_user(db, 1)

    assert isinstance(first, ConversationList)
    assert isinstance(second, ConversationList)
    assert len(second.conversations) >= 1
