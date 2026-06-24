"""
Knowledge router — topics explorer, people profiles, full-text search.
All data comes from real transcript_segments, meetings, and action_items.
"""
from fastapi import APIRouter, Depends, Query
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_db
from app.auth import get_current_user
from app.models.models import User

router = APIRouter(tags=["Knowledge"])


# ── Topics Explorer ────────────────────────────────────────────────────────────

@router.get("/knowledge/topics")
async def get_topics(
    limit: int = 50,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Extract key topics from meeting summary_json.key_topics arrays.
    Returns topic name, mention count, and last seen timestamp.
    """
    result = await db.execute(
        text("""
            WITH topics_raw AS (
                SELECT
                    jsonb_array_elements_text(
                        COALESCE(summary_json->'key_topics', '[]'::jsonb)
                    ) AS topic,
                    created_at
                FROM meetings
                WHERE org_id = :org_id
                  AND summary_json IS NOT NULL
                  AND summary_json ? 'key_topics'
            )
            SELECT
                topic AS name,
                COUNT(*) AS mention_count,
                MAX(created_at) AS last_seen_at
            FROM topics_raw
            WHERE topic IS NOT NULL AND topic != ''
            GROUP BY topic
            ORDER BY mention_count DESC, last_seen_at DESC
            LIMIT :limit
        """),
        {"org_id": str(current_user.org_id), "limit": limit},
    )
    rows = result.mappings().all()

    topics = []
    for i, row in enumerate(rows):
        count = row["mention_count"]
        # Severity: top 30% = high, next 40% = medium, rest = low
        if i < len(rows) * 0.3:
            severity = "high"
        elif i < len(rows) * 0.7:
            severity = "medium"
        else:
            severity = "low"

        last_seen = row["last_seen_at"]
        if last_seen:
            from datetime import datetime, timezone
            diff = datetime.now(timezone.utc) - last_seen.replace(tzinfo=timezone.utc)
            total_seconds = int(diff.total_seconds())
            if total_seconds < 3600:
                last_used = f"{total_seconds // 60}m ago"
            elif total_seconds < 86400:
                last_used = f"{total_seconds // 3600}h ago"
            else:
                last_used = f"{total_seconds // 86400}d ago"
        else:
            last_used = "unknown"

        topics.append({
            "name": row["name"],
            "count": int(count),
            "severity": severity,
            "last_used": last_used,
        })

    return topics


# ── Decisions Timeline ─────────────────────────────────────────────────────────

@router.get("/knowledge/decisions")
async def get_decisions_timeline(
    limit: int = 20,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Pull decisions from meeting summary_json.decisions arrays.
    Returns list of {decision, meeting_title, meeting_date}.
    """
    result = await db.execute(
        text("""
            WITH decisions_raw AS (
                SELECT
                    jsonb_array_elements_text(
                        COALESCE(summary_json->'decisions', '[]'::jsonb)
                    ) AS decision,
                    title AS meeting_title,
                    created_at AS meeting_date
                FROM meetings
                WHERE org_id = :org_id
                  AND summary_json IS NOT NULL
                  AND summary_json ? 'decisions'
            )
            SELECT decision, meeting_title, meeting_date
            FROM decisions_raw
            WHERE decision IS NOT NULL AND decision != ''
            ORDER BY meeting_date DESC
            LIMIT :limit
        """),
        {"org_id": str(current_user.org_id), "limit": limit},
    )
    rows = result.mappings().all()
    return [
        {
            "decision": row["decision"],
            "meeting_title": row["meeting_title"],
            "meeting_date": row["meeting_date"].isoformat() if row["meeting_date"] else None,
        }
        for row in rows
    ]


# ── People Profiles ────────────────────────────────────────────────────────────

@router.get("/knowledge/people")
async def get_people(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Aggregate speaker stats from transcript_segments.
    Returns speaker name, total talk time, meeting count, word count.
    """
    result = await db.execute(
        text("""
            SELECT
                ts.speaker_name AS name,
                COUNT(DISTINCT ts.meeting_id) AS meeting_count,
                ROUND(SUM(ts.end_ms - ts.start_ms) / 60000.0, 1) AS talk_minutes,
                SUM(array_length(string_to_array(trim(ts.text), ' '), 1)) AS word_count
            FROM transcript_segments ts
            JOIN meetings m ON m.id = ts.meeting_id
            WHERE m.org_id = :org_id
              AND ts.speaker_name NOT IN ('', 'Unknown', 'Speaker_A', 'Speaker_B', 'Speaker_C', 'Speaker_D')
            GROUP BY ts.speaker_name
            ORDER BY meeting_count DESC, talk_minutes DESC
            LIMIT 50
        """),
        {"org_id": str(current_user.org_id)},
    )
    rows = result.mappings().all()
    return [
        {
            "name": row["name"],
            "meeting_count": int(row["meeting_count"]),
            "talk_minutes": float(row["talk_minutes"] or 0),
            "word_count": int(row["word_count"] or 0),
        }
        for row in rows
    ]


# ── Full-Text Search ───────────────────────────────────────────────────────────

@router.get("/search")
async def global_search(
    q: str = Query(..., min_length=1),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Search across: meetings (title), transcript segments (text), 
    action items (title), decisions (from summary_json).
    """
    if not q or len(q.strip()) < 2:
        return {"meetings": [], "transcripts": [], "action_items": [], "decisions": []}

    like = f"%{q.lower()}%"
    org_id = str(current_user.org_id)

    # Meetings
    meetings_r = await db.execute(
        text("""
            SELECT id, title, status, platform, started_at, duration_seconds
            FROM meetings
            WHERE org_id = :org_id AND LOWER(title) LIKE :q
            ORDER BY started_at DESC LIMIT 10
        """),
        {"org_id": org_id, "q": like},
    )

    # Transcript segments
    transcripts_r = await db.execute(
        text("""
            SELECT ts.id, ts.text, ts.speaker_name, ts.start_ms,
                   m.id AS meeting_id, m.title AS meeting_title
            FROM transcript_segments ts
            JOIN meetings m ON m.id = ts.meeting_id
            WHERE m.org_id = :org_id AND LOWER(ts.text) LIKE :q
            ORDER BY m.started_at DESC
            LIMIT 15
        """),
        {"org_id": org_id, "q": like},
    )

    # Action items
    actions_r = await db.execute(
        text("""
            SELECT id, title, status, priority, assignee_name, due_date
            FROM action_items
            WHERE org_id = :org_id AND LOWER(title) LIKE :q
            ORDER BY created_at DESC LIMIT 10
        """),
        {"org_id": org_id, "q": like},
    )

    # Decisions from summary_json
    decisions_r = await db.execute(
        text("""
            WITH dec AS (
                SELECT
                    jsonb_array_elements_text(
                        COALESCE(summary_json->'decisions', '[]'::jsonb)
                    ) AS decision,
                    title AS meeting_title,
                    id AS meeting_id,
                    created_at
                FROM meetings
                WHERE org_id = :org_id
                  AND summary_json IS NOT NULL
                  AND summary_json ? 'decisions'
            )
            SELECT decision, meeting_title, meeting_id, created_at
            FROM dec
            WHERE LOWER(decision) LIKE :q
            ORDER BY created_at DESC
            LIMIT 10
        """),
        {"org_id": org_id, "q": like},
    )

    def ms_to_time(ms: int) -> str:
        s = ms // 1000
        return f"{s // 60:02d}:{s % 60:02d}"

    return {
        "meetings": [
            {
                "id": str(r["id"]), "title": r["title"], "status": r["status"],
                "platform": r["platform"],
                "started_at": r["started_at"].isoformat() if r["started_at"] else None,
            }
            for r in meetings_r.mappings().all()
        ],
        "transcripts": [
            {
                "id": str(r["id"]),
                "text": r["text"][:200],
                "speaker": r["speaker_name"],
                "time": ms_to_time(r["start_ms"] or 0),
                "meeting_id": str(r["meeting_id"]),
                "meeting_title": r["meeting_title"],
            }
            for r in transcripts_r.mappings().all()
        ],
        "action_items": [
            {
                "id": str(r["id"]), "title": r["title"], "status": r["status"],
                "priority": r["priority"], "assignee_name": r["assignee_name"],
                "due_date": r["due_date"].isoformat() if r["due_date"] else None,
            }
            for r in actions_r.mappings().all()
        ],
        "decisions": [
            {
                "decision": r["decision"],
                "meeting_title": r["meeting_title"],
                "meeting_id": str(r["meeting_id"]),
            }
            for r in decisions_r.mappings().all()
        ],
    }
