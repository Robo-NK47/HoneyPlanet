"""POST /chat — converse with the trip agent (reads/edits the plan + tasks, searches web)."""

from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from trip_planner.api.auth import require_auth
from trip_planner.chat.agent import run_chat
from trip_planner.db import SessionDep

router = APIRouter(tags=["chat"])


class ChatTurn(BaseModel):
    role: str
    content: str


class ChatTurnIn(BaseModel):
    """A history turn from the client — validated and length-bounded."""

    role: Literal["user", "assistant"]
    content: str = Field(max_length=8000)


class ChatRequest(BaseModel):
    message: str = Field(min_length=1, max_length=4000)
    history: list[ChatTurnIn] = Field(default_factory=list, max_length=50)


class ChatResponse(BaseModel):
    reply: str
    changed: bool  # the plan changed -> client reloads
    tasks_changed: bool = False  # the task board changed -> client refreshes tasks only
    history: list[ChatTurn]


@router.post("/chat", response_model=ChatResponse, dependencies=[Depends(require_auth)])
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
            reply=f"Sorry — something went wrong: {exc}",
            changed=False,
            history=[ChatTurn(role=t.role, content=t.content) for t in req.history],
        )
    return ChatResponse(
        reply=reply,
        changed=plan_changed,
        tasks_changed=tasks_changed,
        history=[ChatTurn(role=m["role"], content=m["content"]) for m in new_history],
    )
