from logging import getLogger
from typing import Any, AsyncGenerator, Dict, List, Tuple

from fastapi_cache.decorator import cache
from opentelemetry import trace
from sqlalchemy.orm import Session

from ppback.db.ppdb_schemas import Conv, ConvPrivacyMembers, UserInfo
from ppback.secu.sec_utils import get_hashed_password

tracer = trace.get_tracer(__name__)
logger = getLogger("ppback.db.dbfuncs")


def key_builder(
    func: callable, namespace: str = "", *, request, response, args, kwargs
):
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


def add_users(session: Session, users: List[Tuple[str, str]]):
    """Add users to the database."""
    allu = []
    for k, p in users:
        # create a user named fanf
        u = UserInfo(
            name=k, nickname=k, email=f"{k}@{k}", salted_password=get_hashed_password(p)
        )
        session.add(u)
        session.commit()
        allu.append(u)
    return allu


def create_convo(session: Session, name: str, users: List[int]):
    """Create a conversation and add users to it."""
    # create a conversation
    c1 = Conv(label=name)
    session.add(c1)
    session.commit()

    for user_id in users:
        cpm = ConvPrivacyMembers(conv_id=c1.id, user_id=user_id, role="member")
        session.add(cpm)
    session.commit()


@cache(300, key_builder=key_builder)
async def get_conversation_list_for_user(
    session_builder: AsyncGenerator[Session, Session], user_id: int
) -> List[Dict[str, Any]]:
    """Get a list of conversations for a specific user."""
    logger.debug(f"Fetching conversations for user {user_id}")
    with tracer.start_as_current_span("get_conversation_list_for_user_db"):
        session: Session = await anext(session_builder())
        convs = (
            session.query(Conv.id, Conv.label)
            .join(ConvPrivacyMembers, Conv.id == ConvPrivacyMembers.conv_id)
            .filter(ConvPrivacyMembers.user_id == user_id)
            .all()
        )
        return [{"id": c.id, "label": c.label} for c in convs]


@cache(300, key_builder=key_builder)
def membersof(session: Session, convo_id: int) -> List[Dict]:
    """
    Get the members of a conversation
    """
    logger.info(f"Fetching members of convo {convo_id}")
    return [
        member.to_dict()
        for member in (
            session.query(ConvPrivacyMembers)
            .filter((ConvPrivacyMembers.conv_id == convo_id))
            .all()
        )
    ]


@cache(300, key_builder=key_builder)
async def hook_user(session: Session, uid: int) -> dict:
    """Fetch a user by ID."""
    with tracer.start_as_current_span("hook_user_db"):
        user: UserInfo = session.query(UserInfo).filter(UserInfo.id == uid).first()
        return user.to_dict()


@cache(300, key_builder=key_builder)
async def allusers(session_builder: AsyncGenerator[Session, Session]) -> List[Dict]:
    """Fetch all users from the database."""
    logger.info("Fetching all users from the database")
    with tracer.start_as_current_span("allusers_db"):
        session: Session = await anext(session_builder())
        allu = session.query(UserInfo).all()
        return [{"id": u.id, "name": u.name, "nickname": u.nickname} for u in allu]


@cache(300, key_builder=key_builder)
async def user_allowed_in_convo(
    session_builder: AsyncGenerator[Session, Session], uid: int, convo_id: int
) -> bool:
    with tracer.start_as_current_span("hook_user_db"):
        session: Session = await anext(session_builder())
        return (
            session.query(ConvPrivacyMembers)
            .filter(
                (ConvPrivacyMembers.user_id == uid)
                & (ConvPrivacyMembers.conv_id == convo_id)
            )
            .count()
        ) == 1
