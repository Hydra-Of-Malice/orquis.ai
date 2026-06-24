"""
Summaries router — summary retrieval and regeneration.
"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_db
from app.auth import get_current_user
from app.models.models import Meeting, User

router = APIRouter(tags=["Summaries"])


@router.get("/meetings/{meeting_id}/summary")
async def get_summary(
    meeting_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    result = await db.execute(select(Meeting).where(Meeting.id == meeting_id))
    rec = result.scalar_one_or_none()
    if not rec:
        raise HTTPException(status_code=404, detail="Meeting not found")

    return {
        "meeting_id": meeting_id,
        "summary_md": rec.summary_md,
        "summary_json": rec.summary_json,
        "health_score": rec.health_score,
        "engagement_score": rec.engagement_score,
        "sentiment": rec.sentiment,
    }


@router.post("/meetings/{meeting_id}/summary/regenerate")
async def regenerate_summary(
    meeting_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Re-trigger the summarization Celery task for this meeting."""
    result = await db.execute(select(Meeting).where(Meeting.id == meeting_id))
    rec = result.scalar_one_or_none()
    if not rec:
        raise HTTPException(status_code=404, detail="Meeting not found")

    try:
        from celery_client import summarise_meeting
        task = summarise_meeting.delay(meeting_id)
        return {"ok": True, "task_id": task.id}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to trigger re-summarization: {e}")
