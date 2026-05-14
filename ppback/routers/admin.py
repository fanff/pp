import logging
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from opentelemetry import trace
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from ppback.db.ppdb_schemas import Conv, ConvMember, UserInfo
from ppback.deps import get_db, require_admin
from ppback.ppschema import (
    AdminConvOut,
    AdminSetConvMemberRoleRequest,
    AdminSetRoleRequest,
    AdminUserOut,
)

logger = logging.getLogger("ppback")
tracer = trace.get_tracer(__name__)

router = APIRouter(dependencies=[Depends(require_admin)])


@router.get("/admin/users", response_model=list[AdminUserOut])
async def admin_list_users(
    session: Annotated[AsyncSession, Depends(get_db)],
):
    users = (await session.execute(select(UserInfo).order_by(UserInfo.id))).scalars().all()
    return [
        AdminUserOut(
            id=u.id,
            name=u.name,
            nickname=u.nickname,
            is_admin=u.is_admin,
            created_at=u.created_at,
        )
        for u in users
    ]


@router.post("/admin/users/{user_id}/role")
async def admin_set_user_role(
    user_id: int,
    body: AdminSetRoleRequest,
    session: Annotated[AsyncSession, Depends(get_db)],
):
    user = await session.get(UserInfo, user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    user.is_admin = body.is_admin
    await session.commit()
    return {"status": "ok", "user_id": user_id, "is_admin": user.is_admin}


@router.get("/admin/conv", response_model=list[AdminConvOut])
async def admin_list_convs(
    session: Annotated[AsyncSession, Depends(get_db)],
):
    convs = (await session.execute(select(Conv).order_by(Conv.id))).scalars().all()
    result = []
    for c in convs:
        count = (
            await session.execute(
                select(func.count()).select_from(ConvMember).where(ConvMember.conv_id == c.id)
            )
        ).scalar_one()
        result.append(
            AdminConvOut(
                id=c.id,
                label=c.label,
                member_count=count,
                created_at=c.created_at,
            )
        )
    return result


@router.post("/admin/conv/{conv_id}/members/{user_id}/role")
async def admin_set_conv_member_role(
    conv_id: int,
    user_id: int,
    body: AdminSetConvMemberRoleRequest,
    session: Annotated[AsyncSession, Depends(get_db)],
):
    conv = await session.get(Conv, conv_id)
    if not conv:
        raise HTTPException(status_code=404, detail="Conversation not found")
    user = await session.get(UserInfo, user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    valid_roles = {"owner", "admin", "member", "viewer"}
    if body.role not in valid_roles:
        raise HTTPException(status_code=400, detail=f"Invalid role. Must be one of: {', '.join(sorted(valid_roles))}")
    member = (
        (
            await session.execute(
                select(ConvMember).where(
                    (ConvMember.conv_id == conv_id) & (ConvMember.user_id == user_id)
                )
            )
        )
        .scalars()
        .first()
    )
    if not member:
        raise HTTPException(status_code=404, detail="User is not a member of this conversation")
    member.role = body.role
    await session.commit()
    return {"status": "ok", "conv_id": conv_id, "user_id": user_id, "role": member.role}
