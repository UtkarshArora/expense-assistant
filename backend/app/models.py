import uuid
from datetime import datetime, timezone

from sqlalchemy import JSON, Column
from sqlmodel import Field, SQLModel


def utcnow() -> datetime:
    # Naive UTC — matches the TIMESTAMP WITHOUT TIME ZONE columns SQLModel
    # generates by default; keeps writes and comparisons consistent.
    return datetime.now(timezone.utc).replace(tzinfo=None)


class Conversation(SQLModel, table=True):
    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    title: str = "New conversation"
    created_at: datetime = Field(default_factory=utcnow)


class Message(SQLModel, table=True):
    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    conversation_id: uuid.UUID = Field(foreign_key="conversation.id", index=True)
    role: str  # "user" | "assistant"
    content: str
    created_at: datetime = Field(default_factory=utcnow)


class ToolCall(SQLModel, table=True):
    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    message_id: uuid.UUID = Field(foreign_key="message.id", index=True)
    name: str
    input: dict = Field(default_factory=dict, sa_column=Column(JSON))
    output: str
    created_at: datetime = Field(default_factory=utcnow)
