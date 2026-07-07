"""
Meetings router — full meeting lifecycle CRUD + bot control.
"""
import os
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import FileResponse, StreamingResponse
from pydantic import BaseModel
from sqlalchemy import delete, select, update, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_db
from app.auth import get_current_user
from app.models.models import (
    Meeting, TranscriptSegment, ActionItem, MeetingAnalytics,
    MeetingSpeakerTrack, User,
)
from app.services import bot_manager

router = APIRouter(tags=["Meetings"])


# ── Request Schemas ────────────────────────────────────────────────────────────

class StartMeetingRequest(BaseModel):
    url: str
    display_name: Optional[str] = None
    visual_capture_mode: Optional[str] = "disabled"


class StatusUpdateRequest(BaseModel):
    status: str


class ParticipantsUpdateRequest(BaseModel):
    participant_names: list[str]


class CompleteRequest(BaseModel):
    wav_path: str
    participant_names: list[str]
    participant_count: Optional[int] = None
    audio_size_bytes: Optional[int] = None


class VideoReadyRequest(BaseModel):
    video_path: str


class UpdateMeetingRequest(BaseModel):
    title: Optional[str] = None


# ── Slot reaper ────────────────────────────────────────────────────────────────

async def _reap_stale_slots(db: AsyncSession):
    from datetime import timedelta
    cutoff = datetime.now(timezone.utc) - timedelta(seconds=90)
    stuck = await db.execute(
        select(Meeting).where(
            Meeting.status.in_(["joining", "lobby"]),
            Meeting.started_at < cutoff,
        )
    )
    for rec in stuck.scalars().all():
        rec.status = "error"
    await db.commit()

    occupants = list(bot_manager._slot_map.items())
    for slot, rid in occupants:
        if not rid or rid == "pending":
            continue
        row = await db.execute(select(Meeting.status).where(Meeting.id == rid))
        status = row.scalar_one_or_none()
        if status is None or status not in ("joining", "lobby", "recording"):
            await bot_manager.free_slot(rid)


# ── Endpoints ──────────────────────────────────────────────────────────────────

@router.post("/meetings/start")
async def start_meeting(
    req: StartMeetingRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    await _reap_stale_slots(db)

    slot = await bot_manager.allocate_slot("pending")
    if slot is None:
        raise HTTPException(status_code=429, detail="No available bot slots (max 4 concurrent)")

    platform = "meet" if "meet.google.com" in req.url else "teams"
    valid_capture_modes = {
        "disabled", "screenshot_1s", "screenshot_2s",
        "screenshot_5s", "screenshot_10s", "video",
    }
    capture_mode = req.visual_capture_mode or "disabled"
    if capture_mode not in valid_capture_modes:
        capture_mode = "disabled"

    meeting = Meeting(
        title=req.display_name or "Meeting",
        meeting_url=req.url,
        platform=platform,
        status="joining",
        started_at=datetime.now(timezone.utc),
        bot_slot_index=slot,
        org_id=current_user.org_id,
        created_by=current_user.id,
        visual_capture_mode=capture_mode,
    )
    db.add(meeting)
    await db.commit()
    await db.refresh(meeting)

    bot_manager._slot_map[slot] = meeting.id
    bot_manager.spawn_bot(meeting.id, req.url, slot, visual_capture_mode=capture_mode)
    return {"meeting_id": meeting.id, "slot": slot}


@router.get("/meetings/active")
async def active_meetings(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    result = await db.execute(
        select(Meeting).where(
            Meeting.status.in_(["joining", "lobby", "recording"]),
            Meeting.org_id == current_user.org_id,
        )
    )
    recs = result.scalars().all()
    return [
        {
            "id": r.id, "title": r.title, "status": r.status,
            "bot_slot_index": r.bot_slot_index,
            "started_at": r.started_at.isoformat() if r.started_at else None,
            "participant_count": r.participant_count or len(r.participant_names or []),
            "platform": r.platform,
        }
        for r in recs
    ]


@router.get("/meetings")
async def list_meetings(
    status: Optional[str] = None,
    q: Optional[str] = None,
    platform: Optional[str] = None,
    from_date: Optional[str] = None,
    to_date: Optional[str] = None,
    limit: int = 50,
    offset: int = 0,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    query = (
        select(Meeting)
        .where(Meeting.org_id == current_user.org_id)
        .order_by(Meeting.created_at.desc())
    )
    if status:
        query = query.where(Meeting.status == status)
    if platform:
        query = query.where(Meeting.platform == platform)
    if q:
        query = query.where(Meeting.title.ilike(f"%{q}%"))
    if from_date:
        parsed_from = datetime.fromisoformat(from_date.replace("Z", "+00:00"))
        query = query.where(Meeting.started_at >= parsed_from)
    if to_date:
        parsed_to = datetime.fromisoformat(to_date.replace("Z", "+00:00"))
        query = query.where(Meeting.started_at <= parsed_to)
    query = query.limit(limit).offset(offset)

    result = await db.execute(query)
    recs = result.scalars().all()

    return [
        {
            "id": r.id,
            "title": r.title,
            "meeting_url": r.meeting_url,
            "platform": r.platform,
            "status": r.status,
            "started_at": r.started_at.isoformat() if r.started_at else None,
            "ended_at": r.ended_at.isoformat() if r.ended_at else None,
            "duration_seconds": r.duration_seconds,
            "participant_count": r.participant_count or len(r.participant_names or []),
            "participant_names": r.participant_names or [],
            "health_score": r.health_score,
            "engagement_score": r.engagement_score,
            "sentiment": r.sentiment
            or (r.summary_json or {}).get("sentiment") if isinstance(r.summary_json, dict) else r.sentiment,
            "audio_size_bytes": r.audio_size_bytes,
            "created_at": r.created_at.isoformat() if r.created_at else None,
            "action_item_count": None,  # loaded separately if needed
        }
        for r in recs
    ]


@router.get("/meetings/{meeting_id}")
async def get_meeting(
    meeting_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    result = await db.execute(select(Meeting).where(Meeting.id == meeting_id))
    rec = result.scalar_one_or_none()
    if not rec:
        raise HTTPException(status_code=404, detail="Meeting not found")

    # Action item count
    ai_count_result = await db.execute(
        select(func.count()).where(ActionItem.meeting_id == meeting_id)
    )
    ai_count = ai_count_result.scalar() or 0

    # Analytics
    analytics_result = await db.execute(
        select(MeetingAnalytics).where(MeetingAnalytics.meeting_id == meeting_id)
    )
    analytics = analytics_result.scalar_one_or_none()

    # Video availability
    if rec.video_path and rec.video_path.startswith("http"):
        has_video = True
    else:
        has_video = bool(rec.video_path and os.path.isfile(rec.video_path))

    return {
        "id": rec.id,
        "title": rec.title,
        "meeting_url": rec.meeting_url,
        "platform": rec.platform,
        "status": rec.status,
        "started_at": rec.started_at.isoformat() if rec.started_at else None,
        "ended_at": rec.ended_at.isoformat() if rec.ended_at else None,
        "duration_seconds": rec.duration_seconds,
        "participant_count": rec.participant_count or 0,
        "participant_names": rec.participant_names or [],
        "audio_size_bytes": rec.audio_size_bytes,
        "summary_md": rec.summary_md,
        "summary_json": rec.summary_json,
        "health_score": rec.health_score,
        "engagement_score": rec.engagement_score,
        "sentiment": rec.sentiment,
        "visual_capture_mode": rec.visual_capture_mode or "disabled",
        "has_video": has_video,
        "action_item_count": ai_count,
        "analytics": {
            "engagement_score": analytics.engagement_score if analytics else None,
            "health_score": analytics.health_score if analytics else None,
            "sentiment_score": analytics.sentiment_score if analytics else None,
            "sentiment_timeline": analytics.sentiment_timeline if analytics else [],
            "talk_time_per_speaker": analytics.talk_time_per_speaker if analytics else {},
            "decisions_count": analytics.decisions_count if analytics else 0,
            "questions_count": analytics.questions_count if analytics else 0,
        } if analytics else None,
    }


@router.patch("/meetings/{meeting_id}")
async def update_meeting(
    meeting_id: str,
    req: UpdateMeetingRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    result = await db.execute(select(Meeting).where(Meeting.id == meeting_id))
    rec = result.scalar_one_or_none()
    if not rec:
        raise HTTPException(status_code=404, detail="Meeting not found")
    if req.title is not None:
        rec.title = req.title
    await db.commit()
    return {"ok": True}


@router.post("/meetings/{meeting_id}/stop")
async def stop_meeting(
    meeting_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    result = await db.execute(select(Meeting).where(Meeting.id == meeting_id))
    rec = result.scalar_one_or_none()
    if not rec:
        raise HTTPException(status_code=404, detail="Meeting not found")
    if rec.status not in ("joining", "lobby", "recording"):
        raise HTTPException(status_code=400, detail="Meeting is not active")
    rec.status = "processing"
    rec.ended_at = datetime.now(timezone.utc)
    await db.commit()
    return {"ok": True}


@router.delete("/meetings/{meeting_id}")
async def delete_meeting(
    meeting_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    result = await db.execute(select(Meeting).where(Meeting.id == meeting_id))
    rec = result.scalar_one_or_none()
    if not rec:
        raise HTTPException(status_code=404, detail="Meeting not found")
    if rec.status in ("joining", "lobby", "recording"):
        raise HTTPException(status_code=409, detail="Cannot delete an active meeting. Stop it first.")

    wav_path = rec.wav_path or ""
    rec_dir = os.path.dirname(wav_path) if wav_path and not wav_path.startswith("http") else ""
    bytes_freed = 0

    await db.execute(delete(TranscriptSegment).where(TranscriptSegment.meeting_id == meeting_id))
    await db.execute(delete(ActionItem).where(ActionItem.meeting_id == meeting_id))
    await db.execute(delete(MeetingSpeakerTrack).where(MeetingSpeakerTrack.meeting_id == meeting_id))
    await db.delete(rec)
    await db.commit()

    if rec_dir and os.path.isdir(rec_dir):
        import shutil
        try:
            for root, _dirs, files in os.walk(rec_dir):
                for f in files:
                    try:
                        bytes_freed += os.path.getsize(os.path.join(root, f))
                    except OSError:
                        pass
            shutil.rmtree(rec_dir, ignore_errors=True)
        except Exception as exc:
            print(f"[delete_meeting] Failed to remove {rec_dir}: {exc}", flush=True)

    return {"ok": True, "bytes_freed": bytes_freed}


@router.get("/meetings/{meeting_id}/audio")
async def get_meeting_audio(
    meeting_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    result = await db.execute(select(Meeting).where(Meeting.id == meeting_id))
    rec = result.scalar_one_or_none()
    if not rec:
        raise HTTPException(status_code=404, detail="Meeting not found")
    if not rec.wav_path:
        raise HTTPException(status_code=404, detail="No audio file for this meeting")

    if rec.wav_path.startswith("http"):
        try:
            from app.services.azure_blob import generate_sas_url
            sas_url = generate_sas_url(rec.wav_path)
            from fastapi.responses import RedirectResponse
            return RedirectResponse(url=sas_url, status_code=307)
        except Exception as exc:
            raise HTTPException(status_code=502, detail=f"Could not generate audio URL: {exc}")

    if not os.path.exists(rec.wav_path):
        raise HTTPException(status_code=404, detail="Audio file not found on disk")
    return FileResponse(rec.wav_path, media_type="audio/wav")


@router.get("/meetings/{meeting_id}/video")
async def get_meeting_video(
    meeting_id: str,
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    result = await db.execute(select(Meeting).where(Meeting.id == meeting_id))
    rec = result.scalar_one_or_none()
    if not rec:
        raise HTTPException(status_code=404, detail="Meeting not found")
    if not rec.video_path:
        raise HTTPException(status_code=404, detail="No video captured for this meeting")

    if rec.video_path.startswith("http"):
        try:
            from app.services.azure_blob import generate_sas_url
            from fastapi.responses import RedirectResponse
            return RedirectResponse(url=generate_sas_url(rec.video_path), status_code=307)
        except Exception as exc:
            raise HTTPException(status_code=502, detail=f"Could not generate video URL: {exc}")

    if not os.path.isfile(rec.video_path):
        raise HTTPException(status_code=404, detail="Video file not found on disk")

    file_size = os.path.getsize(rec.video_path)
    range_header = request.headers.get("range")

    if not range_header:
        return StreamingResponse(
            _iter_file(rec.video_path, 0, file_size - 1),
            status_code=200,
            media_type="video/mp4",
            headers={"Content-Length": str(file_size), "Accept-Ranges": "bytes"},
        )

    try:
        range_val = range_header.replace("bytes=", "").strip()
        start_str, end_str = range_val.split("-", 1)
        start = int(start_str) if start_str else 0
        end = int(end_str) if end_str else file_size - 1
    except (ValueError, IndexError):
        raise HTTPException(status_code=416, detail="Invalid Range header")

    end = min(end, file_size - 1)
    if start >= file_size or start > end:
        raise HTTPException(status_code=416, detail=f"Range not satisfiable")

    return StreamingResponse(
        _iter_file(rec.video_path, start, end),
        status_code=206,
        media_type="video/mp4",
        headers={
            "Content-Range": f"bytes {start}-{end}/{file_size}",
            "Content-Length": str(end - start + 1),
            "Accept-Ranges": "bytes",
        },
    )


def _iter_file(path: str, start: int, end: int, chunk_size: int = 1024 * 256):
    with open(path, "rb") as f:
        f.seek(start)
        remaining = end - start + 1
        while remaining > 0:
            data = f.read(min(chunk_size, remaining))
            if not data:
                break
            remaining -= len(data)
            yield data


# ── Bot-facing slot management ─────────────────────────────────────────────────

@router.post("/meetings/{meeting_id}/release-slot")
async def release_slot(meeting_id: str):
    """Called by bot-runner when bot exits (crash or normal end)."""
    await bot_manager.free_slot(meeting_id)
    return {"ok": True}


@router.patch("/meetings/{meeting_id}/status")
async def update_status(
    meeting_id: str,
    req: StatusUpdateRequest,
    db: AsyncSession = Depends(get_db),
):
    """Called internally by bot-runner to update meeting status."""
    result = await db.execute(select(Meeting).where(Meeting.id == meeting_id))
    rec = result.scalar_one_or_none()
    if not rec:
        raise HTTPException(status_code=404, detail="Meeting not found")
    rec.status = req.status
    await db.commit()
    return {"ok": True}


@router.patch("/meetings/{meeting_id}/participants")
async def update_participants(
    meeting_id: str,
    req: ParticipantsUpdateRequest,
    db: AsyncSession = Depends(get_db),
):
    """Called by bot to update participant list in real-time."""
    result = await db.execute(select(Meeting).where(Meeting.id == meeting_id))
    rec = result.scalar_one_or_none()
    if not rec:
        raise HTTPException(status_code=404, detail="Meeting not found")
    rec.participant_names = req.participant_names
    rec.participant_count = len(req.participant_names)
    await db.commit()
    return {"ok": True}


@router.post("/meetings/{meeting_id}/video-ready")
async def video_ready(
    meeting_id: str,
    req: VideoReadyRequest,
    db: AsyncSession = Depends(get_db),
):
    """Called by bot-runner after screen.mp4 is finalized."""
    result = await db.execute(select(Meeting).where(Meeting.id == meeting_id))
    rec = result.scalar_one_or_none()
    if not rec:
        raise HTTPException(status_code=404, detail="Meeting not found")
    rec.video_path = req.video_path
    await db.commit()
    return {"ok": True}
