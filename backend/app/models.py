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


class User(SQLModel, table=True):
    """Local mirror of an Auth0 user, upserted from token claims per request.

    Auth0 is the source of truth for role/department/employee_name; these
    columns are refreshed on every authenticated request.
    """

    __tablename__ = "app_user"  # "user" is a reserved word in Postgres

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    auth0_sub: str = Field(unique=True, index=True)
    email: str | None = None
    display_name: str | None = None
    role: str  # "employee" | "manager" | "admin"
    department: str | None = None
    employee_name: str | None = None
    created_at: NaiveDatetime = Field(default_factory=utcnow)
    last_seen_at: NaiveDatetime = Field(default_factory=utcnow)


class Conversation(SQLModel, table=True):
    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    user_id: uuid.UUID = Field(foreign_key="app_user.id", index=True)
    title: str = "New conversation"
    created_at: NaiveDatetime = Field(default_factory=utcnow)


class Message(SQLModel, table=True):
    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    conversation_id: uuid.UUID = Field(foreign_key="conversation.id", index=True)
    role: str  # "user" | "assistant"
    content: str
    # True when the agent hit its step limit and the reply may be partial.
    truncated: bool = False
    created_at: NaiveDatetime = Field(default_factory=utcnow)


class ToolCall(SQLModel, table=True):
    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    message_id: uuid.UUID = Field(foreign_key="message.id", index=True)
    name: str
    input: dict = Field(default_factory=dict, sa_column=Column(JSON))
    output: str
    created_at: NaiveDatetime = Field(default_factory=utcnow)
