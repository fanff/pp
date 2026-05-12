from sqlalchemy import Column, Float, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.orm import relationship, declarative_base

Base = declarative_base()


class ConvoMessage(Base):
    __tablename__ = "convomessage"
    id = Column(Integer, primary_key=True, index=True)
    content = Column(
        String,
    )
    sender_id = Column(Integer, ForeignKey("userinfo.id"))
    convchanges = relationship("Convchanges", back_populates="convo_message")



class UserInfo(Base):
    __tablename__ = "userinfo"
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, unique=True, index=True)
    email = Column(String)
    nickname = Column(String)
    salted_password = Column(String)

    def to_dict(self):
        return {c.name: getattr(self, c.name) for c in self.__table__.columns}

    @classmethod
    def from_dict(cls, data: dict):
        return cls(**{c.name: data.get(c.name) for c in cls.__table__.columns})


class ConvPrivacyMembers(Base):
    __tablename__ = "conv_privacy_members"
    __table_args__ = (UniqueConstraint("conv_id", "user_id", name="conv_user_uc"),)
    id = Column(Integer, primary_key=True, index=True)
    conv_id = Column(Integer, ForeignKey("conversations.id"))
    user_id = Column(Integer, ForeignKey("userinfo.id"))
    role = Column(
        String,
        default="member",
    )

    def to_dict(self):
        return {c.name: getattr(self, c.name) for c in self.__table__.columns}


class ConvStartingPoint(Base):
    __tablename__ = "conv_starting_points"
    id = Column(Integer, primary_key=True, index=True)
    parent_id = Column(Integer, ForeignKey("conversations.id"))
    parent_ts = Column(Float)


class Conv(Base):
    __tablename__ = "conversations"
    id = Column(Integer, primary_key=True, index=True)
    label = Column(
        String,
    )
    parent_id = Column(Integer, ForeignKey("conversations.id"), nullable=True)
    parent_ts = Column(Float, nullable=True)


class Convchanges(Base):
    __tablename__ = "convchanges"
    id = Column(Integer, primary_key=True, index=True)
    ts = Column(Float)  # time stamps seconds
    conv_id = Column(Integer, ForeignKey("conversations.id"))
    change_type = Column(String)
    change_id = Column(Integer, ForeignKey("convomessage.id"))
    convo_message = relationship(
        "ConvoMessage", back_populates="convchanges", uselist=False
    )
