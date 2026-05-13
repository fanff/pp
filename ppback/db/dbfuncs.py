import time
from logging import getLogger
from typing import Any, Callable

from fastapi_cache import KeyBuilder
from fastapi_cache.decorator import cache
from opentelemetry import trace
from ppback.ppschema import ConversationItem, ConversationList
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from ppback.db.ppdb_schemas import (
    Conv,
    ConvMember,
    FriendRequest,
    Friendship,
    InviteCode,
    UserInfo,
)
from ppback.secu.sec_utils import get_hashed_password

tracer = trace.get_tracer(__name__)
logger = getLogger("ppback.db.dbfuncs")


def key_builder(
    func: Callable, namespace: str = "", *, request: Any, response: Any, args, kwargs
) -> str:
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
    allu: list[UserInfo] = []
    for k, p in users:
        u = UserInfo(
            name=k, nickname=k, email=f"{k}@{k}", salted_password=get_hashed_password(p)
        )
        session.add(u)
        await session.commit()
        await session.refresh(u)
        allu.append(u)
    return allu


async def create_convo(
    session: AsyncSession,
    name: str,
    users: list[UserInfo],
    creator_id: int | None = None,
) -> tuple[int, str]:
    c1 = Conv(label=name)
    session.add(c1)
    await session.commit()
    await session.refresh(c1)

    for user in users:
        role = "owner" if user.id == creator_id else "member"
        cm = ConvMember(conv_id=c1.id, user_id=user.id, role=role)
        session.add(cm)
    await session.commit()
    return (int(c1.id), str(c1.label))


@cache(300, key_builder=key_builder)
async def _get_conversation_list_for_user_cached(
    session: AsyncSession, user_id: int
) -> dict[str, Any]:
    logger.debug(f"Fetching conversations for user {user_id}")
    with tracer.start_as_current_span("get_conversation_list_for_user_db"):
        convs = (
            (
                await session.execute(
                    select(Conv.id, Conv.label)
                    .join(ConvMember, Conv.id == ConvMember.conv_id)
                    .where(ConvMember.user_id == user_id)
                )
            )
            .all()
        )
        conversations = []
        for c in convs:
            members_query = await session.execute(
                select(ConvMember.user_id).where(ConvMember.conv_id == c.id)
            )
            members = list(members_query.scalars().all())
            conversations.append(
                ConversationItem(id=c.id, label=c.label, members=members).model_dump()
            )
        return {"conversations": conversations}


async def get_conversation_list_for_user(
    session: AsyncSession, user_id: int
) -> ConversationList:
    cached_value = await _get_conversation_list_for_user_cached(session, user_id)
    return ConversationList.model_validate(cached_value)


@cache(300, key_builder=key_builder)
async def membersof(
    session: AsyncSession, convo_id: int
) -> list[dict[str, Any]]:
    logger.info(f"Fetching members of convo {convo_id}")
    members = (
        (
            await session.execute(
                select(ConvMember).where(ConvMember.conv_id == convo_id)
            )
        )
        .scalars()
        .all()
    )
    return [member.to_dict() for member in members]


@cache(300, key_builder=key_builder)
async def _hook_user_cached(
    session: AsyncSession, uid: int
) -> dict[str, Any] | None:
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
    logger.info("Fetching all users from the database")
    with tracer.start_as_current_span("allusers_db"):
        allu = (await session.execute(select(UserInfo))).scalars().all()
        return [
            {"id": u.id, "name": u.name, "nickname": u.nickname} for u in allu
        ]


@cache(300, key_builder=key_builder)
async def user_allowed_in_convo(
    session: AsyncSession, uid: int, convo_id: int
) -> bool:
    with tracer.start_as_current_span("user_allowed_in_convo_db"):
        count_stmt = (
            select(func.count())
            .select_from(ConvMember)
            .where(
                (ConvMember.user_id == uid) & (ConvMember.conv_id == convo_id)
            )
        )
        count = (await session.execute(count_stmt)).scalar_one()
        return count == 1


async def user_can_write_in_convo(
    session: AsyncSession, uid: int, convo_id: int
) -> bool:
    with tracer.start_as_current_span("user_can_write_in_convo_db"):
        result = (
            (
                await session.execute(
                    select(ConvMember.role).where(
                        (ConvMember.user_id == uid)
                        & (ConvMember.conv_id == convo_id)
                    )
                )
            )
            .scalar_one_or_none()
        )
        if result is None:
            return False
        return result in ("owner", "admin", "member")


async def create_invite_code(
    session: AsyncSession, creator_id: int
) -> InviteCode:
    import secrets

    code = secrets.token_urlsafe(16)
    ic = InviteCode(code=code, creator_id=creator_id)
    session.add(ic)
    await session.commit()
    await session.refresh(ic)
    return ic


async def submit_invite_code(
    session: AsyncSession, code: str, user_id: int
) -> FriendRequest:
    ic = (
        (
            await session.execute(
                select(InviteCode).where(
                    (InviteCode.code == code) & (InviteCode.status == "active")
                )
            )
        )
        .scalars()
        .first()
    )
    if ic is None:
        raise ValueError("Invalid or expired invite code")

    ic.status = "used"
    ic.used_at = time.time()
    ic.used_by_id = user_id

    fr = FriendRequest(
        from_user_id=user_id,
        to_user_id=ic.creator_id,
        invite_code_id=ic.id,
    )
    session.add(fr)
    await session.commit()
    await session.refresh(fr)
    return fr


async def accept_friend_request(
    session: AsyncSession, request_id: int, user_id: int
) -> Friendship:
    fr = (
        (
            await session.execute(
                select(FriendRequest).where(
                    (FriendRequest.id == request_id)
                    & (FriendRequest.to_user_id == user_id)
                    & (FriendRequest.status == "pending")
                )
            )
        )
        .scalars()
        .first()
    )
    if fr is None:
        raise ValueError("Friend request not found or already resolved")

    fr.status = "accepted"
    fr.updated_at = time.time()

    a, b = sorted([fr.from_user_id, fr.to_user_id])
    fs = Friendship(user_a_id=a, user_b_id=b)
    session.add(fs)
    await session.commit()
    await session.refresh(fs)
    return fs


async def reject_friend_request(
    session: AsyncSession, request_id: int, user_id: int
) -> None:
    fr = (
        (
            await session.execute(
                select(FriendRequest).where(
                    (FriendRequest.id == request_id)
                    & (FriendRequest.to_user_id == user_id)
                    & (FriendRequest.status == "pending")
                )
            )
        )
        .scalars()
        .first()
    )
    if fr is None:
        raise ValueError("Friend request not found or already resolved")

    fr.status = "rejected"
    fr.updated_at = time.time()
    await session.commit()


async def get_friend_requests(
    session: AsyncSession, user_id: int
) -> list[dict[str, Any]]:
    result = (
        (
            await session.execute(
                select(FriendRequest).where(
                    (FriendRequest.from_user_id == user_id)
                    | (FriendRequest.to_user_id == user_id)
                )
            )
        )
        .scalars()
        .all()
    )
    return [
        {
            "id": r.id,
            "from_user_id": r.from_user_id,
            "to_user_id": r.to_user_id,
            "status": r.status,
        }
        for r in result
    ]


async def get_friends(
    session: AsyncSession, user_id: int
) -> list[dict[str, Any]]:
    fsa = (
        (
            await session.execute(
                select(Friendship)
                .where(
                    (Friendship.user_a_id == user_id)
                    | (Friendship.user_b_id == user_id)
                )
            )
        )
        .scalars()
        .all()
    )
    friend_ids = [
        fs.user_b_id if fs.user_a_id == user_id else fs.user_a_id
        for fs in fsa
    ]

    if not friend_ids:
        return []

    users = (
        (
            await session.execute(
                select(UserInfo).where(UserInfo.id.in_(friend_ids))
            )
        )
        .scalars()
        .all()
    )
    user_map = {u.id: u for u in users}

    results = []
    for fs in fsa:
        fid = fs.user_b_id if fs.user_a_id == user_id else fs.user_a_id
        u = user_map.get(fid)
        if u:
            results.append(
                {
                    "user_id": u.id,
                    "name": u.name,
                    "nickname": u.nickname,
                    "since": fs.created_at,
                }
            )
    return results


async def get_visible_users(
    session: AsyncSession, user_id: int
) -> list[dict[str, Any]]:
    friend_ids = set()
    fsa = (
        (
            await session.execute(
                select(Friendship).where(
                    (Friendship.user_a_id == user_id)
                    | (Friendship.user_b_id == user_id)
                )
            )
        )
        .scalars()
        .all()
    )
    for fs in fsa:
        fid = fs.user_b_id if fs.user_a_id == user_id else fs.user_a_id
        friend_ids.add(fid)

    conv_peer_ids = set()
    user_convs = (
        (
            await session.execute(
                select(ConvMember.conv_id).where(ConvMember.user_id == user_id)
            )
        )
        .scalars()
        .all()
    )
    if user_convs:
        peers = (
            (
                await session.execute(
                    select(ConvMember.user_id).where(
                        ConvMember.conv_id.in_(user_convs)
                    )
                )
            )
            .scalars()
            .all()
        )
        conv_peer_ids.update(peers)

    request_ids = set()
    reqs = (
        (
            await session.execute(
                select(FriendRequest.from_user_id).where(
                    (FriendRequest.to_user_id == user_id)
                    & (FriendRequest.status == "pending")
                )
            )
        )
        .scalars()
        .all()
    )
    request_ids.update(reqs)

    visible_ids = friend_ids | conv_peer_ids | request_ids | {user_id}
    if not visible_ids:
        return []

    users = (
        (
            await session.execute(
                select(UserInfo).where(UserInfo.id.in_(visible_ids))
            )
        )
        .scalars()
        .all()
    )
    return [{"id": u.id, "name": u.name, "nickname": u.nickname} for u in users]
