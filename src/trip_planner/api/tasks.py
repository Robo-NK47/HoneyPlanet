"""Task board CRUD — /tasks. Booking/prep to-dos categorized by date and importance."""

from __future__ import annotations

from datetime import date

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, ConfigDict
from sqlalchemy import select

from trip_planner.db import SessionDep
from trip_planner.models import Task

router = APIRouter(prefix="/tasks", tags=["tasks"])
_IMPORTANCE = {"low", "medium", "high"}
_ORDER = {"high": 0, "medium": 1, "low": 2}


class TaskOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    title: str
    notes: str | None = None
    due_date: date | None = None
    importance: str
    done: bool


class TaskCreate(BaseModel):
    title: str
    notes: str | None = None
    due_date: date | None = None
    importance: str = "medium"


class TaskUpdate(BaseModel):
    title: str | None = None
    notes: str | None = None
    due_date: date | None = None
    importance: str | None = None
    done: bool | None = None


@router.get("", response_model=list[TaskOut])
async def list_tasks(session: SessionDep) -> list[Task]:
    rows = (await session.execute(select(Task))).scalars().all()
    return sorted(rows, key=lambda t: (t.due_date or date.max, _ORDER.get(t.importance, 1), t.id))


@router.post("", response_model=TaskOut)
async def create_task(body: TaskCreate, session: SessionDep) -> Task:
    importance = body.importance if body.importance in _IMPORTANCE else "medium"
    task = Task(
        title=body.title[:512],
        notes=body.notes,
        due_date=body.due_date,
        importance=importance,
        done=False,
    )
    session.add(task)
    await session.commit()
    await session.refresh(task)
    return task


@router.patch("/{task_id}", response_model=TaskOut)
async def update_task(task_id: int, body: TaskUpdate, session: SessionDep) -> Task:
    task = await session.get(Task, task_id)
    if task is None:
        raise HTTPException(status_code=404, detail="Task not found")
    data = body.model_dump(exclude_unset=True)
    if data.get("importance") not in _IMPORTANCE:
        data.pop("importance", None)
    if data.get("title"):
        data["title"] = data["title"][:512]
    for key, value in data.items():
        setattr(task, key, value)
    await session.commit()
    await session.refresh(task)
    return task


@router.delete("/{task_id}")
async def delete_task(task_id: int, session: SessionDep) -> dict:
    task = await session.get(Task, task_id)
    if task is None:
        raise HTTPException(status_code=404, detail="Task not found")
    await session.delete(task)
    await session.commit()
    return {"ok": True}
