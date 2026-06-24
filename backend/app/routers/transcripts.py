"""
Transcripts router — real-time segment posting + retrieval.
"""
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_db
from app.auth import get_current_user
from app.models.models import Meeting, TranscriptSegment, User

router = APIRouter(tags=["Transcripts"])


class SegmentCreateRequest(BaseModel):
    id: str
    speaker_name: str
    start_ms: int
    end_ms: int
    text: str
    confidence: Optional[float] = 1.0


class SpeakerRenameRequest(BaseModel):
    old_name: str
    new_name: str


@router.get("/meetings/{meeting_id}/transcript")
async def get_transcript(
    meeting_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    result = await db.execute(
        select(TranscriptSegment)
        .where(TranscriptSegment.meeting_id == meeting_id)
        .order_by(TranscriptSegment.start_ms)
    )
    segs = result.scalars().all()
    return [
        {
            "id": s.id,
            "speaker_name": s.speaker_name,
            "speaker_id": s.speaker_id,
            "start_ms": s.start_ms,
            "end_ms": s.end_ms,
            "text": s.text,
            "confidence": s.confidence,
        }
        for s in segs
    ]


@router.post("/meetings/{meeting_id}/transcript/segments")
async def add_segment(
    meeting_id: str,
    req: SegmentCreateRequest,
    db: AsyncSession = Depends(get_db),
):
    """Bot posts live transcript segments here (called internally)."""
    seg = TranscriptSegment(
        id=req.id,
        meeting_id=meeting_id,
        speaker_name=req.speaker_name,
        start_ms=req.start_ms,
        end_ms=req.end_ms,
        text=req.text,
        confidence=req.confidence,
    )
    db.add(seg)
    await db.commit()

    # Publish to Redis for WebSocket clients
    try:
        import redis.asyncio as aioredis
        import json
        import os
        redis_url = os.getenv("REDIS_URL", "redis://redis:6379/0")
        r = aioredis.from_url(redis_url)
        await r.publish(
            f"zapper:live:{meeting_id}",
            json.dumps({
                "type": "segment",
                "payload": {
                    "id": req.id,
                    "speaker_name": req.speaker_name,
                    "start_ms": req.start_ms,
                    "end_ms": req.end_ms,
                    "text": req.text,
                }
            })
        )
        await r.aclose()
    except Exception as e:
        print(f"[transcripts] Redis publish failed (non-fatal): {e}", flush=True)

    return {"ok": True}


@router.patch("/meetings/{meeting_id}/transcript/speaker")
async def rename_speaker(
    meeting_id: str,
    req: SpeakerRenameRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Rename all segments from old_name to new_name for this meeting."""
    await db.execute(
        update(TranscriptSegment)
        .where(
            TranscriptSegment.meeting_id == meeting_id,
            TranscriptSegment.speaker_name == req.old_name,
        )
        .values(speaker_name=req.new_name)
    )
    await db.commit()
    return {"ok": True}
