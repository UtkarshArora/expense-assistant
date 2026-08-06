import uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..db import get_session
from ..models import Conversation, Message, ToolCall
from ..schemas import ConversationDetailOut, ConversationOut, MessageOut, ToolCallOut

router = APIRouter()


@router.get("/conversations", response_model=list[ConversationOut])
async def list_conversations(
    session: AsyncSession = Depends(get_session),
) -> list[ConversationOut]:
    result = await session.execute(
        select(Conversation).order_by(Conversation.created_at.desc())
    )
    return [
        ConversationOut(id=c.id, title=c.title, created_at=c.created_at)
        for c in result.scalars().all()
    ]


@router.get("/conversations/{conversation_id}", response_model=ConversationDetailOut)
async def get_conversation(
    conversation_id: uuid.UUID, session: AsyncSession = Depends(get_session)
) -> ConversationDetailOut:
    conversation = await session.get(Conversation, conversation_id)
    if conversation is None:
        raise HTTPException(status_code=404, detail="Conversation not found")

    messages = (
        (
            await session.execute(
                select(Message)
                .where(Message.conversation_id == conversation_id)
                .order_by(Message.created_at)
            )
        )
        .scalars()
        .all()
    )

    tool_calls_by_message: dict[uuid.UUID, list[ToolCall]] = {}
    if messages:
        tool_calls = (
            (
                await session.execute(
                    select(ToolCall).where(
                        ToolCall.message_id.in_([m.id for m in messages])
                    )
                )
            )
            .scalars()
            .all()
        )
        for tc in tool_calls:
            tool_calls_by_message.setdefault(tc.message_id, []).append(tc)

    return ConversationDetailOut(
        id=conversation.id,
        title=conversation.title,
        created_at=conversation.created_at,
        messages=[
            MessageOut(
                id=m.id,
                role=m.role,
                content=m.content,
                created_at=m.created_at,
                tool_calls=[
                    ToolCallOut(
                        id=t.id, name=t.name, input=t.input, output=t.output, created_at=t.created_at
                    )
                    for t in tool_calls_by_message.get(m.id, [])
                ],
            )
            for m in messages
        ],
    )
