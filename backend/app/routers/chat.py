"""
AI Chat router — SSE streaming with RAG over meeting transcripts.
Stores chat sessions and messages in DB.
"""
import json
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_db
from app.auth import get_current_user
from app.models.models import (
    ChatSession, ChatMessage, Meeting, TranscriptSegment, ActionItem, User,
)
from app.services.llm_client import chat_stream_async

router = APIRouter(tags=["Chat"])

SYSTEM_PROMPT = (
    "You are Zapper AI, an intelligent meeting intelligence assistant. "
    "You have access to the user's meeting transcripts, summaries, and action items. "
    "Answer questions concisely and specifically using the provided meeting context. "
    "When citing information from a meeting, mention the meeting title and speaker name. "
    "Use markdown formatting for lists and emphasis where appropriate."
)


class ChatMessageSchema(BaseModel):
    role: str
    content: str


class SendMessageRequest(BaseModel):
    content: str
    meeting_id: Optional[str] = None


class CreateSessionRequest(BaseModel):
    title: Optional[str] = None
    meeting_id: Optional[str] = None


# ── Sessions ───────────────────────────────────────────────────────────────────

@router.get("/chat/sessions")
async def list_sessions(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    result = await db.execute(
        select(ChatSession)
        .where(ChatSession.user_id == current_user.id)
        .order_by(ChatSession.updated_at.desc())
        .limit(50)
    )
    sessions = result.scalars().all()
    return [
        {
            "id": s.id,
            "title": s.title or "New Chat",
            "meeting_id": s.meeting_id,
            "created_at": s.created_at.isoformat() if s.created_at else None,
            "updated_at": s.updated_at.isoformat() if s.updated_at else None,
        }
        for s in sessions
    ]


@router.post("/chat/sessions", status_code=201)
async def create_session(
    req: CreateSessionRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    session = ChatSession(
        user_id=current_user.id,
        meeting_id=req.meeting_id,
        title=req.title or "New Chat",
    )
    db.add(session)
    await db.commit()
    await db.refresh(session)
    return {"id": session.id, "title": session.title}


@router.get("/chat/sessions/{session_id}")
async def get_session(
    session_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    result = await db.execute(
        select(ChatSession).where(
            ChatSession.id == session_id,
            ChatSession.user_id == current_user.id,
        )
    )
    session = result.scalar_one_or_none()
    if not session:
        raise HTTPException(status_code=404, detail="Chat session not found")

    msgs_result = await db.execute(
        select(ChatMessage)
        .where(ChatMessage.session_id == session_id)
        .order_by(ChatMessage.created_at)
    )
    messages = msgs_result.scalars().all()

    return {
        "id": session.id,
        "title": session.title,
        "meeting_id": session.meeting_id,
        "messages": [
            {
                "id": m.id,
                "role": m.role,
                "content": m.content,
                "citations": m.citations or [],
                "created_at": m.created_at.isoformat() if m.created_at else None,
            }
            for m in messages
        ],
    }


# ── Message streaming (SSE) ────────────────────────────────────────────────────

@router.post("/chat/sessions/{session_id}/messages")
async def send_message(
    session_id: str,
    req: SendMessageRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    result = await db.execute(
        select(ChatSession).where(
            ChatSession.id == session_id,
            ChatSession.user_id == current_user.id,
        )
    )
    session = result.scalar_one_or_none()
    if not session:
        raise HTTPException(status_code=404, detail="Chat session not found")

    # Build RAG context
    context_parts = []
    citations = []
    meeting_id = req.meeting_id or session.meeting_id

    if meeting_id:
        rec_r = await db.execute(select(Meeting).where(Meeting.id == meeting_id))
        rec = rec_r.scalar_one_or_none()
        if rec:
            context_parts.append(f"MEETING: {rec.title or 'Untitled'}\nDate: {rec.started_at.date() if rec.started_at else 'unknown'}")
            if rec.summary_md:
                context_parts.append(f"SUMMARY:\n{rec.summary_md[:2000]}")
            seg_r = await db.execute(
                select(TranscriptSegment)
                .where(TranscriptSegment.meeting_id == meeting_id)
                .order_by(TranscriptSegment.start_ms)
                .limit(150)
            )
            segs = seg_r.scalars().all()
            if segs:
                transcript_lines = []
                for s in segs:
                    start_min = s.start_ms // 60000
                    start_sec = (s.start_ms % 60000) // 1000
                    transcript_lines.append(f"[{start_min:02d}:{start_sec:02d}] {s.speaker_name}: {s.text}")
                    citations.append({
                        "meeting_id": meeting_id,
                        "meeting_title": rec.title,
                        "segment_id": s.id,
                        "speaker": s.speaker_name,
                        "snippet": s.text[:100],
                        "start_ms": s.start_ms,
                    })
                context_parts.append(f"TRANSCRIPT:\n" + "\n".join(transcript_lines))
    else:
        # Cross-meeting context: last 5 completed meetings
        recs_r = await db.execute(
            select(Meeting)
            .where(
                Meeting.status == "done",
                Meeting.org_id == current_user.org_id,
            )
            .order_by(Meeting.created_at.desc())
            .limit(5)
        )
        recs = recs_r.scalars().all()
        for r in recs:
            if r.summary_md:
                context_parts.append(
                    f"MEETING ({r.started_at.date() if r.started_at else 'unknown'}): {r.title}\n"
                    + r.summary_md[:600]
                )
        ai_r = await db.execute(
            select(ActionItem)
            .where(
                ActionItem.status != "done",
                ActionItem.org_id == current_user.org_id,
            )
            .limit(20)
        )
        items = ai_r.scalars().all()
        if items:
            context_parts.append(
                "OPEN ACTION ITEMS:\n"
                + "\n".join(f"- {a.assignee_name or 'Unassigned'}: {a.title}" for a in items)
            )

    context_str = "\n\n".join(context_parts)
    system_msg = SYSTEM_PROMPT
    if context_str:
        system_msg += f"\n\nCONTEXT:\n{context_str}"

    # Load message history
    hist_r = await db.execute(
        select(ChatMessage)
        .where(ChatMessage.session_id == session_id)
        .order_by(ChatMessage.created_at.desc())
        .limit(20)
    )
    history = list(reversed(hist_r.scalars().all()))

    messages = [{"role": "system", "content": system_msg}]
    for h in history[-10:]:
        messages.append({"role": h.role, "content": h.content})
    messages.append({"role": "user", "content": req.content})

    # Save user message
    user_msg = ChatMessage(
        session_id=session_id,
        role="user",
        content=req.content,
    )
    db.add(user_msg)

    # Update session title if first message
    if not history:
        session.title = req.content[:60]
    session.updated_at = __import__("datetime").datetime.now(__import__("datetime").timezone.utc)
    await db.commit()

    # SSE stream
    full_response = []

    async def event_stream():
        async for chunk in chat_stream_async(messages):
            full_response.append(chunk)
            payload = json.dumps({"choices": [{"delta": {"content": chunk}}]})
            yield f"data: {payload}\n\n"
        yield "data: [DONE]\n\n"

        # Save assistant message after stream completes
        assistant_content = "".join(full_response)
        async with db.__class__(db.get_bind()) as new_db:
            pass  # Handled below via background task pattern

    async def event_stream_with_save():
        response_chunks = []
        async for chunk in chat_stream_async(messages):
            response_chunks.append(chunk)
            payload = json.dumps({"choices": [{"delta": {"content": chunk}}]})
            yield f"data: {payload}\n\n"

        yield "data: [DONE]\n\n"

        # Persist assistant reply
        try:
            assistant_text = "".join(response_chunks)
            from app.db import AsyncSessionLocal
            async with AsyncSessionLocal() as save_db:
                assistant_msg = ChatMessage(
                    session_id=session_id,
                    role="assistant",
                    content=assistant_text,
                    citations=citations[:5] if citations else None,
                )
                save_db.add(assistant_msg)
                await save_db.commit()
        except Exception as e:
            print(f"[chat] Failed to save assistant message: {e}", flush=True)

    return StreamingResponse(
        event_stream_with_save(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
