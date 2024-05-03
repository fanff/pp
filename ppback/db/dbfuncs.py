from typing import Dict, List, Tuple

from fastapi_cache.decorator import cache
from opentelemetry import trace

from ppback.db.ppdb_schemas import Conv, ConvPrivacyMembers, UserInfo

from ..secu.sec_utils import get_hashed_password

tracer = trace.get_tracer(__name__)


def key_builder(func, namespace: str = "", *, request, response, args, kwargs):

    values = [namespace, func.__name__] + [
        str(k) for k in args if isinstance(k, (str, int, float))
    ]

    for k, v in kwargs:
        if k != "session":
            values.append(str(v))
    return ":".join(values)


def add_users(session, users: List[Tuple[str, str]]):
    """give me the session and the list of [(nick:password)]"""
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


def create_convo(session, name: str, users: List[UserInfo]):
    # create a conversation
    c1 = Conv(label=name)
    session.add(c1)
    session.commit()

    for u in users:

        cpm = ConvPrivacyMembers(conv_id=c1.id, user_id=u.id, role="member")
        session.add(cpm)
    session.commit()


@cache(300, key_builder=key_builder)
def membersof(session, convo_id: int) -> List[Dict]:
    """
    Get the members of a conversation
    """
    return [
        _.to_dict()
        for _ in (
            session.query(ConvPrivacyMembers)
            .filter((ConvPrivacyMembers.conv_id == convo_id))
            .all()
        )
    ]


@cache(300, key_builder=key_builder)
async def hook_user(session, uid):
    with tracer.start_as_current_span("hook_user_db"):
        user: UserInfo = session.query(UserInfo).filter(UserInfo.id == uid).first()
        return user.to_dict()


@cache(300, key_builder=key_builder)
async def allusers(session):
    with tracer.start_as_current_span("allusers_db"):
        allu = session.query(UserInfo).all()
        return [{"id": u.id, "name": u.name, "nickname": u.nickname} for u in allu]


@cache(300, key_builder=key_builder)
async def user_allowed_in_convo(session, uid, convo_id):
    with tracer.start_as_current_span("hook_user_db"):
        return (
            session.query(ConvPrivacyMembers)
            .filter(
                (ConvPrivacyMembers.user_id == uid)
                & (ConvPrivacyMembers.conv_id == convo_id)
            )
            .count()
        )
