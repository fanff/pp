from typing import Literal

from pydantic import BaseModel, Field, ConfigDict


class MsgInputSchema(BaseModel):
    content: str = Field(..., description="Content of the user message")
    conversation_id: int = Field(..., description="id of the conversation to post in")


class MsgOutputSchema(BaseModel):
    status: str = Field(..., description="Status of the message post. Usually 'ok'")
    messageid: int | None = Field(None, description="The stored message id.")


class MessageSchema(BaseModel):
    id: int = Field(..., description="Monotonic message id, usable as cursor.")
    content: str = Field(..., description="The content of the message.")
    sender: int = Field(
        ..., description="The unique identifier of the sender of the message."
    )
    message_type: str = Field("text", description="Type of the message (text, image, audio, custom).")
    ts: float = Field(..., description="The timestamp when the message was sent.")

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "id": 1,
                "content": "Hello, this is a test message.",
                "sender": 1,
                "message_type": "text",
                "ts": 129887837.3443,
            }
        }
    )


class MessageWS(BaseModel):
    type: Literal["message.created"] = "message.created"
    conversation_id: int
    message_id: int
    sender_id: int
    ts: float


class ConversationItem(BaseModel):
    id: int
    label: str
    members: list[int]


class ConversationList(BaseModel):
    conversations: list[ConversationItem]


class ConversationCreate(BaseModel):
    label: str
    members: list[int]


class InviteCodeCreate(BaseModel):
    pass


class InviteCodeOut(BaseModel):
    code: str


class FriendRequestOut(BaseModel):
    id: int
    from_user_id: int
    to_user_id: int
    status: str


class FriendRequestSubmit(BaseModel):
    invite_code: str


class FriendRequestAccept(BaseModel):
    pass


class FriendshipOut(BaseModel):
    user_id: int
    name: str
    nickname: str
    since: float
