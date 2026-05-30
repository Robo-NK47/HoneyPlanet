"""POST /chat — converse with the trip agent (reads/edits the plan + tasks, searches web)."""

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
    changed: bool  # the plan changed -> client reloads
    tasks_changed: bool = False  # the task board changed -> client refreshes tasks only
    history: list[ChatTurn]


@router.post("/chat", response_model=ChatResponse)
async def chat(req: ChatRequest, session: SessionDep) -> ChatResponse:
    history = [{"role": t.role, "content": t.content} for t in req.history]
    try:
        reply, plan_changed, tasks_changed, new_history = await run_chat(
            session, req.message, history
        )
        if plan_changed or tasks_changed:
            await session.commit()
    except Exception as exc:  # surface agent/LLM errors to the chat UI instead of a 500
        return ChatResponse(
            reply=f"Sorry — something went wrong: {exc}", changed=False, history=req.history
        )
    return ChatResponse(
        reply=reply,
        changed=plan_changed,
        tasks_changed=tasks_changed,
        history=[ChatTurn(role=m["role"], content=m["content"]) for m in new_history],
    )
