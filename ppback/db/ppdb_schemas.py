from __future__ import annotations

import time

from sqlalchemy import Float, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.dialects.sqlite import JSON
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class ConvoMessage(Base):
    __tablename__ = "convomessage"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    conv_id: Mapped[int] = mapped_column(ForeignKey("conversations.id"), index=True)
    sender_id: Mapped[int] = mapped_column(ForeignKey("userinfo.id"), index=True)
    ts: Mapped[float] = mapped_column(Float, index=True)
    message_type: Mapped[str] = mapped_column(String, default="text", index=True)
    content: Mapped[str] = mapped_column(String)
    payload: Mapped[dict | None] = mapped_column(JSON, nullable=True)


class UserInfo(Base):
    __tablename__ = "userinfo"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    name: Mapped[str] = mapped_column(String, unique=True, index=True)
    email: Mapped[str] = mapped_column(String)
    nickname: Mapped[str] = mapped_column(String)
    salted_password: Mapped[str] = mapped_column(String)
    created_at: Mapped[float | None] = mapped_column(Float, default=time.time)

    def to_dict(self):
        return {c.name: getattr(self, c.name) for c in self.__table__.columns}

    @classmethod
    def from_dict(cls, data: dict):
        return cls(**{c.name: data.get(c.name) for c in cls.__table__.columns})


class ConvMember(Base):
    __tablename__ = "conv_members"
    __table_args__ = (UniqueConstraint("conv_id", "user_id", name="conv_user_uc"),)

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    conv_id: Mapped[int] = mapped_column(ForeignKey("conversations.id"))
    user_id: Mapped[int] = mapped_column(ForeignKey("userinfo.id"))
    role: Mapped[str] = mapped_column(String, default="member")

    def to_dict(self):
        return {c.name: getattr(self, c.name) for c in self.__table__.columns}


class ConvStartingPoint(Base):
    __tablename__ = "conv_starting_points"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    parent_id: Mapped[int] = mapped_column(ForeignKey("conversations.id"))
    parent_ts: Mapped[float] = mapped_column(Float)


class Conv(Base):
    __tablename__ = "conversations"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    label: Mapped[str] = mapped_column(String)
    parent_id: Mapped[int | None] = mapped_column(
        ForeignKey("conversations.id"), nullable=True
    )
    parent_ts: Mapped[float | None] = mapped_column(Float, nullable=True)
    created_at: Mapped[float] = mapped_column(Float, default=time.time)
    updated_at: Mapped[float] = mapped_column(Float, default=time.time, onupdate=time.time)


class InviteCode(Base):
    __tablename__ = "invite_codes"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    code: Mapped[str] = mapped_column(String, unique=True, index=True)
    creator_id: Mapped[int] = mapped_column(ForeignKey("userinfo.id"))
    status: Mapped[str] = mapped_column(String, default="active")
    created_at: Mapped[float] = mapped_column(Float, default=time.time)
    used_at: Mapped[float | None] = mapped_column(Float, nullable=True)
    used_by_id: Mapped[int | None] = mapped_column(ForeignKey("userinfo.id"), nullable=True)


class FriendRequest(Base):
    __tablename__ = "friend_requests"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    from_user_id: Mapped[int] = mapped_column(ForeignKey("userinfo.id"))
    to_user_id: Mapped[int] = mapped_column(ForeignKey("userinfo.id"))
    invite_code_id: Mapped[int | None] = mapped_column(ForeignKey("invite_codes.id"), nullable=True)
    status: Mapped[str] = mapped_column(String, default="pending")
    created_at: Mapped[float] = mapped_column(Float, default=time.time)
    updated_at: Mapped[float] = mapped_column(Float, default=time.time, onupdate=time.time)


class Friendship(Base):
    __tablename__ = "friendships"
    __table_args__ = (UniqueConstraint("user_a_id", "user_b_id", name="friendship_uc"),)

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    user_a_id: Mapped[int] = mapped_column(ForeignKey("userinfo.id"))
    user_b_id: Mapped[int] = mapped_column(ForeignKey("userinfo.id"))
    created_at: Mapped[float] = mapped_column(Float, default=time.time)
