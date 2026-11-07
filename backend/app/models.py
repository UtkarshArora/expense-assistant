import uuid
from datetime import datetime, timezone

from pydantic import NaiveDatetime
from sqlalchemy import JSON, Column
from sqlmodel import Field, SQLModel


def utcnow() -> datetime:
    # Naive UTC, stored in TIMESTAMP WITHOUT TIME ZONE columns. Fields are
    # annotated NaiveDatetime because SQLModel >= 0.0.47 maps a plain
    # `datetime` to TIMESTAMPTZ and rejects naive values.
    return datetime.now(timezone.utc).replace(tzinfo=None)


class Conversation(SQLModel, table=True):
    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    title: str = "New conversation"
    created_at: NaiveDatetime = Field(default_factory=utcnow)


class Message(SQLModel, table=True):
    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    conversation_id: uuid.UUID = Field(foreign_key="conversation.id", index=True)
    role: str  # "user" | "assistant"
    content: str
    created_at: NaiveDatetime = Field(default_factory=utcnow)


class ToolCall(SQLModel, table=True):
    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    message_id: uuid.UUID = Field(foreign_key="message.id", index=True)
    name: str
    input: dict = Field(default_factory=dict, sa_column=Column(JSON))
    output: str
    created_at: NaiveDatetime = Field(default_factory=utcnow)
