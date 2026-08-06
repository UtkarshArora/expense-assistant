import asyncio

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from ..agent import run_agent
from ..db import get_session
from ..models import Conversation, Message, ToolCall
from ..schemas import ChatRequest, ChatResponse, MessageOut, ToolCallOut

router = APIRouter()


@router.post("/chat", response_model=ChatResponse)
async def chat(
    req: ChatRequest, session: AsyncSession = Depends(get_session)
) -> ChatResponse:
    if req.conversation_id is not None:
        conversation = await session.get(Conversation, req.conversation_id)
        if conversation is None:
            raise HTTPException(status_code=404, detail="Conversation not found")
    else:
        conversation = Conversation(title=req.message.strip()[:60] or "New conversation")
        session.add(conversation)
        await session.flush()

    user_message = Message(
        conversation_id=conversation.id, role="user", content=req.message
    )
    session.add(user_message)
    await session.flush()

    # run_agent makes a blocking Anthropic SDK call, so it runs in a worker
    # thread instead of tying up the event loop.
    final_text, tool_calls = await asyncio.to_thread(run_agent, req.message)

    assistant_message = Message(
        conversation_id=conversation.id, role="assistant", content=final_text
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
            tool_calls=[
                ToolCallOut(
                    id=r.id, name=r.name, input=r.input, output=r.output, created_at=r.created_at
                )
                for r in tool_call_rows
            ],
        ),
    )
