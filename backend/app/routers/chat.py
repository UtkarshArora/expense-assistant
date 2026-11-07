import asyncio

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..agent import build_history, run_agent
from ..auth import get_current_user
from ..config import settings
from ..db import get_session
from ..models import Conversation, Message, ToolCall, User, utcnow
from ..schemas import ChatRequest, ChatResponse, MessageOut, ToolCallOut

router = APIRouter()

# How many stored messages (user + assistant) are replayed to the model.
HISTORY_LIMIT = 20


async def _messages_sent_today(session: AsyncSession, user: User) -> int:
    start_of_day = utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
    return await session.scalar(
        select(func.count())
        .select_from(Message)
        .join(Conversation, Message.conversation_id == Conversation.id)
        .where(
            Conversation.user_id == user.id,
            Message.role == "user",
            Message.created_at >= start_of_day,
        )
    )


@router.post("/chat", response_model=ChatResponse)
async def chat(
    req: ChatRequest,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> ChatResponse:
    if await _messages_sent_today(session, user) >= settings.daily_message_limit:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=f"Daily limit of {settings.daily_message_limit} messages reached. "
            "Try again tomorrow (UTC).",
        )

    if req.conversation_id is not None:
        conversation = await session.get(Conversation, req.conversation_id)
        # Someone else's conversation looks exactly like a missing one.
        if conversation is None or conversation.user_id != user.id:
            raise HTTPException(status_code=404, detail="Conversation not found")
        # Text only: ToolCall rows are never loaded into model context.
        recent = (
            await session.execute(
                select(Message.role, Message.content)
                .where(Message.conversation_id == conversation.id)
                .order_by(Message.created_at.desc())
                .limit(HISTORY_LIMIT)
            )
        ).all()
        history = build_history([(r.role, r.content) for r in reversed(recent)])
    else:
        history = []
        conversation = Conversation(
            user_id=user.id, title=req.message.strip()[:60] or "New conversation"
        )
        session.add(conversation)
        await session.flush()

    user_message = Message(
        conversation_id=conversation.id, role="user", content=req.message
    )
    session.add(user_message)
    await session.flush()

    # run_agent makes a blocking Anthropic SDK call, so it runs in a worker
    # thread instead of tying up the event loop.
    final_text, tool_calls, truncated = await asyncio.to_thread(
        run_agent, history, req.message
    )

    assistant_message = Message(
        conversation_id=conversation.id,
        role="assistant",
        content=final_text,
        truncated=truncated,
    )
    session.add(assistant_message)
    await session.flush()

    tool_call_rows = [
        ToolCall(
            message_id=assistant_message.id,
            name=tc["name"],
            input=tc["input"],
            output=tc["output"],
        )
        for tc in tool_calls
    ]
    for row in tool_call_rows:
        session.add(row)

    await session.commit()

    return ChatResponse(
        conversation_id=conversation.id,
        message=MessageOut(
            id=assistant_message.id,
            role=assistant_message.role,
            content=assistant_message.content,
            created_at=assistant_message.created_at,
            truncated=assistant_message.truncated,
            tool_calls=[
                ToolCallOut(
                    id=r.id, name=r.name, input=r.input, output=r.output, created_at=r.created_at
                )
                for r in tool_call_rows
            ],
        ),
    )
