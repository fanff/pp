"""Schema definitions for the API and web socket messages."""

from pydantic import BaseModel, Field


# base schema model for API
class MsgInputSchema(BaseModel):
    content: str = Field(..., description="Content of the user message")
    conversation_id: int = Field(..., description="id of the conversation to post in")


class MsgOutputSchema(BaseModel):
    status: str = Field(..., description="Status of the message post. Usually 'ok'")


class MessageSchema(BaseModel):
    id: int = Field(..., description="The unique identifier of the message.")
    content: str = Field(..., description="The content of the message.")
    sender: int = Field(
        ..., description="The unique identifier of the sender of the message."
    )
    ts: float = Field(..., description="The timestamp when the message was sent.")

    class Config:
        schema_extra = {
            "example": {
                "id": 1,
                "content": "Hello, this is a test message.",
                "sender": 1,
                "ts": 129887837.3443,
            }
        }


# web socket simple schemas
class MessageWS(BaseModel):
    """Model representing a message in a web service context."""

    originator_id: int
    convo_id: int
    content: str
