"""Schema definitions for the API and web socket messages."""

from typing import Literal

from pydantic import BaseModel, Field, ConfigDict


# base schema model for API
class MsgInputSchema(BaseModel):
    content: str = Field(..., description="Content of the user message")
    conversation_id: int = Field(..., description="id of the conversation to post in")


class MsgOutputSchema(BaseModel):
    status: str = Field(..., description="Status of the message post. Usually 'ok'")
    messageid: int | None = Field(None, description="The stored message id.")
    change_id: int | None = Field(
        None,
        description="Exclusive cursor for fetching later conversation history changes.",
    )


class MessageSchema(BaseModel):
    id: int = Field(..., description="The unique identifier of the message.")
    change_id: int = Field(
        ..., description="Monotonic conversation change cursor for resync."
    )
    message_id: int = Field(..., description="The stored message row id.")
    content: str = Field(..., description="The content of the message.")
    sender: int = Field(
        ..., description="The unique identifier of the sender of the message."
    )
    ts: float = Field(..., description="The timestamp when the message was sent.")

    model_config = ConfigDict(
        json_schema_extra = {
            "example": {
                "id": 1,
                "change_id": 1,
                "message_id": 1,
                "content": "Hello, this is a test message.",
                "sender": 1,
                "ts": 129887837.3443,
            }
        }
    )


# web socket simple schemas
class MessageWS(BaseModel):
    """Backend control event telling clients to resync message history."""

    type: Literal["message.created"] = "message.created"
    conversation_id: int
    change_id: int
    message_id: int
    sender_id: int
    ts: float
    watermark: int = Field(
        ..., description="Highest known Convchanges.id included in this event."
    )

class ConversationItem(BaseModel):
    """Model representing a single conversation item."""

    id: int
    label: str
    members: list[int]

class ConversationList(BaseModel):
    """Model representing a list of conversations for a user."""

    conversations: list[ConversationItem]

class ConversationCreate(BaseModel):
    """Model representing the data needed to create a new conversation."""
    label: str
    members: list[int]
