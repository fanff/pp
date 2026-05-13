from logging import getLogger
from typing import Any, Callable

from fastapi_cache import KeyBuilder
from fastapi_cache.decorator import cache
from opentelemetry import trace
from ppback.ppschema import ConversationItem, ConversationList
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from ppback.db.ppdb_schemas import Conv, ConvPrivacyMembers, UserInfo
from ppback.secu.sec_utils import get_hashed_password

tracer = trace.get_tracer(__name__)
logger = getLogger("ppback.db.dbfuncs")

def key_builder(
    func: Callable, namespace: str = "", *, request:Any, response:Any, args, kwargs
) -> str:
    """Build a cache key based on the function name, namespace, and arguments."""
    values = [namespace, func.__name__] + [
        str(k) for k in args if isinstance(k, (str, int, float))
    ]

    for k, v in kwargs.items():
        if k != "session":
            values.append(str(v))
    cache_key = ":".join(values)
    logger.debug(f"Cache key built: {cache_key}")
    return cache_key


async def add_users(
    session: AsyncSession, users: list[tuple[str, str]]
) -> list[UserInfo]:
    """Add users to the database."""
    allu: list[UserInfo] = []
    for k, p in users:
        # create a user named fanf
        u = UserInfo(
            name=k, nickname=k, email=f"{k}@{k}", salted_password=get_hashed_password(p)
        )
        session.add(u)
        await session.commit()
        await session.refresh(u)
        allu.append(u)
    return allu


async def create_convo(
    session: AsyncSession, name: str, users: list[UserInfo]
) -> tuple[int, str]:
    """Create a conversation and add users to it."""
    # create a conversation
    c1 = Conv(label=name)
    session.add(c1)
    await session.commit()
    await session.refresh(c1)
    
    for user in users:
        cpm = ConvPrivacyMembers(conv_id=c1.id, user_id=user.id, role="member")
        session.add(cpm)
    await session.commit()
    return (int(c1.id) , str(c1.label))

 

@cache(300, key_builder=key_builder )
async def _get_conversation_list_for_user_cached(
    session: AsyncSession, user_id: int
) -> dict[str, Any]:
    """Get a list of conversations for a specific user."""
    logger.debug(f"Fetching conversations for user {user_id}")
    with tracer.start_as_current_span("get_conversation_list_for_user_db"):
        convs = (
            (
                await session.execute(
                    select(Conv.id, Conv.label)
                    .join(ConvPrivacyMembers, Conv.id == ConvPrivacyMembers.conv_id)
                    .where(ConvPrivacyMembers.user_id == user_id)
                )
            )
            .all()
        )
        conversations = []
        for c in convs:
            members_query = await session.execute(
                select(ConvPrivacyMembers.user_id).where(ConvPrivacyMembers.conv_id == c.id)
            )
            members = list(members_query.scalars().all())
            conversations.append(ConversationItem(id=c.id, label=c.label, members=members).model_dump())
        return {"conversations": conversations}


async def get_conversation_list_for_user(
    session: AsyncSession, user_id: int
) -> ConversationList:
    cached_value = await _get_conversation_list_for_user_cached(session, user_id)
    return ConversationList.model_validate(cached_value)


@cache(300, key_builder=key_builder)
async def membersof(session: AsyncSession, convo_id: int) -> list[dict[str, Any]]:
    """
    Get the members of a conversation
    """
    logger.info(f"Fetching members of convo {convo_id}")
    members = (
        (
            await session.execute(
                select(ConvPrivacyMembers).where(ConvPrivacyMembers.conv_id == convo_id)
            )
        )
        .scalars()
        .all()
    )
    return [member.to_dict() for member in members]


@cache(300, key_builder=key_builder)
async def _hook_user_cached(session: AsyncSession, uid: int) -> dict[str, Any] | None:
    """Fetch a user by ID."""
    with tracer.start_as_current_span("hook_user_db"):
        user = (
            (
                await session.execute(select(UserInfo).where(UserInfo.id == uid))
            )
            .scalars()
            .first()
        )
        return None if user is None else user.to_dict()


async def hook_user(session: AsyncSession, uid: int) -> UserInfo | None:
    cached_value = await _hook_user_cached(session, uid)
    return None if cached_value is None else UserInfo.from_dict(cached_value)


@cache(300, key_builder=key_builder)
async def allusers(session: AsyncSession) -> list[dict[str, Any]]:
    """Fetch all users from the database."""
    logger.info("Fetching all users from the database")
    with tracer.start_as_current_span("allusers_db"):
        allu = ((await session.execute(select(UserInfo))).scalars().all())
        return [{"id": u.id, "name": u.name, "nickname": u.nickname} for u in allu]


@cache(300, key_builder=key_builder)
async def user_allowed_in_convo(
    session: AsyncSession, uid: int, convo_id: int
) -> bool:
    with tracer.start_as_current_span("hook_user_db"):
        count_stmt = select(func.count()).select_from(ConvPrivacyMembers).where(
            (ConvPrivacyMembers.user_id == uid)
            & (ConvPrivacyMembers.conv_id == convo_id)
        )
        count = (await session.execute(count_stmt)).scalar_one()
        return count == 1
