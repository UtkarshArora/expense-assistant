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
    tool_calls: list[ToolCallOut] = []


class ChatResponse(BaseModel):
    conversation_id: uuid.UUID
    message: MessageOut


class ConversationOut(BaseModel):
    id: uuid.UUID
    title: str
    created_at: datetime


class ConversationDetailOut(ConversationOut):
    messages: list[MessageOut] = []
