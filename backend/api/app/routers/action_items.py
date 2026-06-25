"""
Action items router — full Kanban CRUD with priority, status, integrations.
"""
from datetime import date
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_db
from app.auth import get_current_user
from app.models.models import ActionItem, User

router = APIRouter(tags=["ActionItems"])


class CreateActionItemRequest(BaseModel):
    title: str
    description: Optional[str] = None
    assignee_name: Optional[str] = None
    assignee_id: Optional[str] = None
    status: Optional[str] = "todo"
    priority: Optional[str] = "medium"
    due_date: Optional[str] = None
    meeting_id: Optional[str] = None
    source: Optional[str] = "manual"
    sort_order: Optional[int] = 0


class UpdateActionItemRequest(BaseModel):
    title: Optional[str] = None
    description: Optional[str] = None
    assignee_name: Optional[str] = None
    assignee_id: Optional[str] = None
    status: Optional[str] = None
    priority: Optional[str] = None
    due_date: Optional[str] = None
    sort_order: Optional[int] = None
    jira_id: Optional[str] = None
    linear_id: Optional[str] = None
    notion_id: Optional[str] = None


def _item_response(item: ActionItem) -> dict:
    return {
        "id": item.id,
        "title": item.title,
        "description": item.description,
        "assignee_name": item.assignee_name,
        "assignee_id": item.assignee_id,
        "status": item.status,
        "priority": item.priority,
        "due_date": item.due_date.isoformat() if item.due_date else None,
        "meeting_id": item.meeting_id,
        "source": item.source,
        "sort_order": item.sort_order,
        "jira_id": item.jira_id,
        "linear_id": item.linear_id,
        "notion_id": item.notion_id,
        "created_at": item.created_at.isoformat() if item.created_at else None,
        "updated_at": item.updated_at.isoformat() if item.updated_at else None,
    }


@router.get("/action-items")
async def list_action_items(
    status: Optional[str] = None,
    priority: Optional[str] = None,
    meeting_id: Optional[str] = None,
    assignee_id: Optional[str] = None,
    limit: int = 100,
    offset: int = 0,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    query = (
        select(ActionItem)
        .where(ActionItem.org_id == current_user.org_id)
        .order_by(ActionItem.sort_order, ActionItem.created_at.desc())
    )
    if status:
        query = query.where(ActionItem.status == status)
    if priority:
        query = query.where(ActionItem.priority == priority)
    if meeting_id:
        query = query.where(ActionItem.meeting_id == meeting_id)
    if assignee_id:
        query = query.where(ActionItem.assignee_id == assignee_id)
    query = query.limit(limit).offset(offset)

    result = await db.execute(query)
    return [_item_response(item) for item in result.scalars().all()]


@router.get("/meetings/{meeting_id}/action-items")
async def list_meeting_action_items(
    meeting_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    result = await db.execute(
        select(ActionItem)
        .where(ActionItem.meeting_id == meeting_id)
        .order_by(ActionItem.sort_order, ActionItem.created_at)
    )
    return [_item_response(item) for item in result.scalars().all()]


@router.post("/action-items", status_code=201)
async def create_action_item(
    req: CreateActionItemRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    due = None
    if req.due_date:
        try:
            due = date.fromisoformat(req.due_date)
        except ValueError:
            pass

    item = ActionItem(
        title=req.title,
        description=req.description,
        assignee_name=req.assignee_name,
        assignee_id=req.assignee_id,
        status=req.status or "todo",
        priority=req.priority or "medium",
        due_date=due,
        meeting_id=req.meeting_id,
        org_id=current_user.org_id,
        created_by=current_user.id,
        source=req.source or "manual",
        sort_order=req.sort_order or 0,
    )
    db.add(item)
    await db.commit()
    await db.refresh(item)
    return _item_response(item)


@router.patch("/action-items/{item_id}")
async def update_action_item(
    item_id: str,
    req: UpdateActionItemRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    result = await db.execute(select(ActionItem).where(ActionItem.id == item_id))
    item = result.scalar_one_or_none()
    if not item:
        raise HTTPException(status_code=404, detail="Action item not found")

    if req.title is not None:
        item.title = req.title
    if req.description is not None:
        item.description = req.description
    if req.assignee_name is not None:
        item.assignee_name = req.assignee_name
    if req.assignee_id is not None:
        item.assignee_id = req.assignee_id
    if req.status is not None:
        item.status = req.status
    if req.priority is not None:
        item.priority = req.priority
    if req.due_date is not None:
        try:
            item.due_date = date.fromisoformat(req.due_date)
        except ValueError:
            pass
    if req.sort_order is not None:
        item.sort_order = req.sort_order
    if req.jira_id is not None:
        item.jira_id = req.jira_id
    if req.linear_id is not None:
        item.linear_id = req.linear_id
    if req.notion_id is not None:
        item.notion_id = req.notion_id

    await db.commit()
    await db.refresh(item)
    return _item_response(item)


@router.delete("/action-items/{item_id}")
async def delete_action_item(
    item_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    result = await db.execute(select(ActionItem).where(ActionItem.id == item_id))
    item = result.scalar_one_or_none()
    if not item:
        raise HTTPException(status_code=404, detail="Action item not found")
    await db.delete(item)
    await db.commit()
    return {"ok": True}


@router.get("/action-items/stats")
async def action_item_stats(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Summary strip: total, overdue, completed this week."""
    from datetime import datetime, timezone, timedelta
    today = date.today()
    week_start = today - timedelta(days=today.weekday())

    total_r = await db.execute(
        select(func.count()).where(
            ActionItem.org_id == current_user.org_id,
            ActionItem.status != "done",
        )
    )
    overdue_r = await db.execute(
        select(func.count()).where(
            ActionItem.org_id == current_user.org_id,
            ActionItem.status != "done",
            ActionItem.due_date < today,
        )
    )
    done_week_r = await db.execute(
        select(func.count()).where(
            ActionItem.org_id == current_user.org_id,
            ActionItem.status == "done",
            ActionItem.updated_at >= datetime(week_start.year, week_start.month, week_start.day, tzinfo=timezone.utc),
        )
    )
    return {
        "total_open": total_r.scalar() or 0,
        "overdue": overdue_r.scalar() or 0,
        "completed_this_week": done_week_r.scalar() or 0,
    }
