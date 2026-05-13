from __future__ import annotations

from sqlalchemy import Float, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


class ConvoMessage(Base):
    __tablename__ = "convomessage"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    content: Mapped[str] = mapped_column(String)
    sender_id: Mapped[int] = mapped_column(ForeignKey("userinfo.id"))
    convchanges: Mapped[list["Convchanges"]] = relationship(
        "Convchanges", back_populates="convo_message"
    )



class UserInfo(Base):
    __tablename__ = "userinfo"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    name: Mapped[str] = mapped_column(String, unique=True, index=True)
    email: Mapped[str] = mapped_column(String)
    nickname: Mapped[str] = mapped_column(String)
    salted_password: Mapped[str] = mapped_column(String)

    def to_dict(self):
        return {c.name: getattr(self, c.name) for c in self.__table__.columns}

    @classmethod
    def from_dict(cls, data: dict):
        return cls(**{c.name: data.get(c.name) for c in cls.__table__.columns})


class ConvPrivacyMembers(Base):
    __tablename__ = "conv_privacy_members"
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


class Convchanges(Base):
    __tablename__ = "convchanges"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    ts: Mapped[float] = mapped_column(Float)
    conv_id: Mapped[int] = mapped_column(ForeignKey("conversations.id"))
    change_type: Mapped[str] = mapped_column(String)
    change_id: Mapped[int] = mapped_column(ForeignKey("convomessage.id"))
    convo_message: Mapped[ConvoMessage | None] = relationship(
        "ConvoMessage", back_populates="convchanges", uselist=False
    )
