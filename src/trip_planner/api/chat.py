"""POST /chat — converse with the trip agent (reads/edits the plan, searches the web)."""

from __future__ import annotations

from fastapi import APIRouter
from pydantic import BaseModel

from trip_planner.chat.agent import run_chat
from trip_planner.db import SessionDep

router = APIRouter(tags=["chat"])


class ChatTurn(BaseModel):
    role: str
    content: str


class ChatRequest(BaseModel):
    message: str
    history: list[ChatTurn] = []


class ChatResponse(BaseModel):
    reply: str
    changed: bool
    history: list[ChatTurn]


@router.post("/chat", response_model=ChatResponse)
async def chat(req: ChatRequest, session: SessionDep) -> ChatResponse:
    history = [{"role": t.role, "content": t.content} for t in req.history]
    try:
        reply, changed, new_history = await run_chat(session, req.message, history)
        if changed:
            await session.commit()
    except Exception as exc:  # surface agent/LLM errors to the chat UI instead of a 500
        return ChatResponse(
            reply=f"Sorry — something went wrong: {exc}", changed=False, history=req.history
        )
    return ChatResponse(
        reply=reply,
        changed=changed,
        history=[ChatTurn(role=m["role"], content=m["content"]) for m in new_history],
    )
