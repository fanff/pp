from sqlalchemy import Column, Float, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import relationship

Base = declarative_base()


class ConvoMessage(Base):
    __tablename__ = "convomessage"
    id: int = Column(Integer, primary_key=True, index=True)
    content: str = Column(
        String,
    )
    sender_id: int = Column(Integer, ForeignKey("userinfo.id"))
    convchanges = relationship("Convchanges", back_populates="convo_message")


# for later use.
class AgentPatch(Base):
    __tablename__ = "agent_patches"
    id: int = Column(Integer, primary_key=True, index=True)
    profile_name: str = Column(
        String,
    )
    subprofile_name: str = Column(
        String,
    )


# for later use.
class ItemAssignement(Base):
    __tablename__ = "item_assignements"
    id: int = Column(Integer, primary_key=True, index=True)
    item_name: str = Column(
        String,
    )
    action: str = Column(
        String,
    )  # drop, add, produced


class UserInfo(Base):
    __tablename__ = "userinfo"
    id: int = Column(Integer, primary_key=True, index=True)
    name: str = Column(String, unique=True, index=True)
    email: str = Column(
        String,
    )
    nickname: str = Column(
        String,
    )
    salted_password: str = Column(
        String,
    )


class ConvPrivacyMembers(Base):
    __tablename__ = "conv_privacy_members"
    id: int = Column(Integer, primary_key=True, index=True)
    conv_id: int = Column(Integer, ForeignKey("conversations.id"))
    user_id: int = Column(Integer, ForeignKey("userinfo.id"))
    UniqueConstraint("conv_id", "user_id", name="conv_user_uc")
    role: str = Column(
        String,
    )  # member

    def to_dict(self):
        return {c.name: getattr(self, c.name) for c in self.__table__.columns}


class ConvStartingPoint(Base):
    __tablename__ = "conv_starting_points"
    id: int = Column(Integer, primary_key=True, index=True)
    parent_id: int = Column(Integer, ForeignKey("conversations.id"))
    parent_ts: int = Column(Float)


class Conv(Base):
    __tablename__ = "conversations"
    id: int = Column(Integer, primary_key=True, index=True)
    label: str = Column(
        String,
    )
    parent_id: int = Column(Integer, ForeignKey("conversations.id"), nullable=True)
    parent_ts: int = Column(Float, nullable=True)


class Convchanges(Base):
    __tablename__ = "convchanges"
    id: int = Column(Integer, primary_key=True, index=True)
    ts: float = Column(Float)  # time stamps seconds
    conv_id: int = Column(Integer, ForeignKey("conversations.id"))
    change_type: str = Column(
        String,
    )
    change_id = Column(Integer, ForeignKey("convomessage.id"))
    convo_message = relationship(
        "ConvoMessage", back_populates="convchanges", uselist=False
    )
