"""
Bot internal router — endpoints called by bot-runner (not end-users).
Handles segment ingestion, meeting completion, and video readiness.
"""
import os
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_db
from app.models.models import Meeting, TranscriptSegment
from app.services import bot_manager

router = APIRouter(tags=["Bot Internal"])


class SegmentBatch(BaseModel):
    segments: list[dict]


class CompleteRequest(BaseModel):
    wav_path: str
    participant_names: list[str]
    participant_count: Optional[int] = None
    audio_size_bytes: Optional[int] = None
    duration_seconds: Optional[int] = None


class VideoReadyRequest(BaseModel):
    video_path: str


@router.post("/bot/{meeting_id}/segments")
async def ingest_segments(
    meeting_id: str,
    req: SegmentBatch,
    db: AsyncSession = Depends(get_db),
):
    """Bot posts live transcript segments in batches."""
    import redis.asyncio as aioredis
    import json

    redis_url = os.getenv("REDIS_URL", "redis://redis:6379/0")

    for seg_data in req.segments:
        seg = TranscriptSegment(
            id=seg_data.get("id", str(__import__("uuid").uuid4())),
            meeting_id=meeting_id,
            speaker_name=seg_data.get("speaker_name", "Speaker"),
            speaker_id=seg_data.get("speaker_id"),
            start_ms=seg_data.get("start_ms", 0),
            end_ms=seg_data.get("end_ms", 0),
            text=seg_data.get("text", ""),
            confidence=seg_data.get("confidence", 1.0),
        )
        db.add(seg)

    await db.commit()

    # Publish to Redis for live WebSocket clients
    try:
        r = aioredis.from_url(redis_url)
        for seg_data in req.segments:
            await r.publish(
                f"zapper:live:{meeting_id}",
                json.dumps({"type": "segment", "payload": seg_data})
            )
        await r.aclose()
    except Exception as e:
        print(f"[bot] Redis publish failed (non-fatal): {e}", flush=True)

    return {"ok": True, "count": len(req.segments)}


@router.post("/bot/{meeting_id}/complete")
async def complete_meeting(
    meeting_id: str,
    req: CompleteRequest,
    db: AsyncSession = Depends(get_db),
):
    """Bot posts completion data — triggers post-meeting Celery pipeline."""
    result = await db.execute(select(Meeting).where(Meeting.id == meeting_id))
    rec = result.scalar_one_or_none()
    if not rec:
        raise HTTPException(status_code=404, detail="Meeting not found")

    rec.wav_path = req.wav_path
    rec.participant_names = req.participant_names
    rec.participant_count = req.participant_count or len(req.participant_names)
    rec.audio_size_bytes = req.audio_size_bytes
    rec.duration_seconds = req.duration_seconds
    rec.status = "processing"
    rec.ended_at = datetime.now(timezone.utc)
    await db.commit()

    # Free the bot slot
    await bot_manager.free_slot(meeting_id)

    # Trigger Celery pipeline
    try:
        from celery_client import run_post_meeting_pipeline
        run_post_meeting_pipeline.delay(meeting_id)
        print(f"[bot] Pipeline triggered for {meeting_id}", flush=True)
    except Exception as e:
        print(f"[bot] Failed to trigger pipeline (non-fatal): {e}", flush=True)
        # Mark as error only if pipeline trigger fails completely
        # The pipeline can be re-triggered manually from the UI

    return {"ok": True}


@router.post("/bot/{meeting_id}/video-ready")
async def video_ready(
    meeting_id: str,
    req: VideoReadyRequest,
    db: AsyncSession = Depends(get_db),
):
    """Bot posts this when screen.mp4 is finalized."""
    result = await db.execute(select(Meeting).where(Meeting.id == meeting_id))
    rec = result.scalar_one_or_none()
    if not rec:
        raise HTTPException(status_code=404, detail="Meeting not found")

    rec.video_path = req.video_path
    await db.commit()

    # Enqueue Azure upload if configured
    conn_str = os.getenv("AZURE_STORAGE_CONNECTION_STRING", "")
    if conn_str:
        try:
            from celery_client import upload_video
            upload_video.delay(meeting_id, req.video_path)
        except Exception as e:
            print(f"[bot] Could not enqueue Azure video upload (non-fatal): {e}", flush=True)

    return {"ok": True}


@router.post("/bot/meetings/{meeting_id}/release-slot")
async def release_slot(meeting_id: str):
    await bot_manager.free_slot(meeting_id)
    return {"ok": True}


@router.patch("/bot/meetings/{meeting_id}/status")
async def update_status(
    meeting_id: str,
    body: dict,
    db: AsyncSession = Depends(get_db),
):
    status = body.get("status")
    if not status:
        raise HTTPException(status_code=400, detail="status required")
    result = await db.execute(select(Meeting).where(Meeting.id == meeting_id))
    rec = result.scalar_one_or_none()
    if not rec:
        raise HTTPException(status_code=404, detail="Meeting not found")
    rec.status = status
    await db.commit()
    return {"ok": True}
