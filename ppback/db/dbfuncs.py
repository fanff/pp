from typing import Dict, List, Tuple
from sqlalchemy.orm import Session
from fastapi_cache.decorator import cache
from opentelemetry import trace

from ppback.db.ppdb_schemas import Conv, ConvPrivacyMembers, UserInfo

from ppback.secu.sec_utils import get_hashed_password

tracer = trace.get_tracer(__name__)


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
    return ":".join(values)


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


def create_convo(session: Session, name: str, users: List[UserInfo]):
    """Create a conversation and add users to it."""
    # create a conversation
    c1 = Conv(label=name)
    session.add(c1)
    session.commit()

    for user in users:
        cpm = ConvPrivacyMembers(conv_id=c1.id, user_id=user.id, role="member")
        session.add(cpm)
    session.commit()


@cache(300, key_builder=key_builder)
def membersof(session: Session, convo_id: int) -> List[Dict]:
    """
    Get the members of a conversation
    """
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
async def allusers(session: Session) -> List[Dict]:
    """Fetch all users from the database."""
    with tracer.start_as_current_span("allusers_db"):
        allu = session.query(UserInfo).all()
        return [{"id": u.id, "name": u.name, "nickname": u.nickname} for u in allu]


@cache(300, key_builder=key_builder)
async def user_allowed_in_convo(session: Session, uid: int, convo_id: int) -> bool:
    with tracer.start_as_current_span("hook_user_db"):
        return (
            session.query(ConvPrivacyMembers)
            .filter(
                (ConvPrivacyMembers.user_id == uid)
                & (ConvPrivacyMembers.conv_id == convo_id)
            )
            .count()
        ) == 1
