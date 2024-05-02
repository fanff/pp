from typing import List, Tuple

from secu.sec_utils import get_hashed_password

from ppback.db.ppdb_schemas import Conv, ConvPrivacyMembers, UserInfo


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
