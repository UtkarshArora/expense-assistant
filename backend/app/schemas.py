import uuid
from datetime import datetime

from pydantic import BaseModel


class ChatRequest(BaseModel):
    message: str
    conversation_id: uuid.UUID | None = None


class ToolCallOut(BaseModel):
    id: uuid.UUID
    name: str
    input: dict
    output: str
    created_at: datetime


class MessageOut(BaseModel):
    id: uuid.UUID
    role: str
    content: str
    created_at: datetime
    truncated: bool = False
    tool_calls: list[ToolCallOut] = []


class ChatResponse(BaseModel):
    conversation_id: uuid.UUID
    message: MessageOut


class MeOut(BaseModel):
    id: uuid.UUID
    email: str | None
    display_name: str | None
    role: str
    department: str | None
    employee_name: str | None


class ConversationOut(BaseModel):
    id: uuid.UUID
    title: str
    created_at: datetime


class ConversationDetailOut(ConversationOut):
    messages: list[MessageOut] = []
