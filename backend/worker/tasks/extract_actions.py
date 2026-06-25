"""
Action item extraction from meeting transcript via LLM.
"""
import json
import re

from sqlalchemy import text

from db import get_session
from llm_client import chat_completion


SYSTEM_PROMPT = """Extract all action items and tasks from the meeting transcript.

Return a JSON array:
[
  {
    "title": "Clear, specific action item title (imperative form, max 80 chars)",
    "assignee": "Person assigned, or null if unclear",
    "due": "Due date or deadline if mentioned, as free text, or null",
    "priority": "urgent | high | medium | low",
    "context": "1 sentence of context from the transcript explaining why this was assigned"
  }
]

Rules:
- Only include concrete, actionable tasks (not general statements)
- Priority is 'urgent' if due within 2 days, 'high' if mentioned as important, 'medium' by default, 'low' if non-critical
- Return an empty array [] if there are genuinely no action items
- Do NOT invent tasks — only extract what was explicitly assigned or agreed upon"""


def extract_actions(meeting_id: str, segments: list[dict]) -> list[dict]:
    """Extract action items and write to action_items table."""
    transcript = _build_transcript(segments)
    if not transcript.strip():
        return []

    actions = _call_llm(transcript)
    if not actions:
        return []

    with get_session() as session:
        # Get org_id from the meeting
        row = session.execute(
            text("SELECT org_id FROM meetings WHERE id = :id"),
            {"id": meeting_id},
        ).fetchone()
        org_id = row[0] if row else None

        for action in actions:
            session.execute(
                text("""
                    INSERT INTO action_items
                        (id, meeting_id, org_id, title, description, assignee_name,
                         priority, status, source, created_at, updated_at)
                    VALUES
                        (gen_random_uuid(), :meeting_id, :org_id, :title,
                         :description, :assignee, :priority, 'todo', 'transcript',
                         now(), now())
                    ON CONFLICT DO NOTHING
                """),
                {
                    "meeting_id": meeting_id,
                    "org_id": org_id,
                    "title": (action.get("title") or "")[:200],
                    "description": action.get("context"),
                    "assignee": action.get("assignee"),
                    "priority": action.get("priority") or "medium",
                },
            )
        session.commit()
        print(f"[extract_actions] Wrote {len(actions)} action items for {meeting_id}", flush=True)

    return actions


def _build_transcript(segments: list[dict]) -> str:
    lines = []
    for s in segments:
        if not s.get("text"):
            continue
        start_ms = s.get("offset_ms", 0) or s.get("start_ms", 0)
        start_min = start_ms // 60000
        start_sec = (start_ms % 60000) // 1000
        speaker = s.get("speaker_name", "Unknown")
        lines.append(f"[{start_min:02d}:{start_sec:02d}] {speaker}: {s['text']}")
    return "\n".join(lines)


def _call_llm(transcript: str) -> list[dict]:
    try:
        raw = chat_completion(
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {
                    "role": "user",
                    "content": "Extract all action items from this transcript:\n\n" + transcript,
                },
            ],
            kind="mini",
            temperature=0.1,
            max_tokens=2000,
        )
        cleaned = re.sub(r"```(?:json)?\s*|\s*```", "", raw).strip()
        parsed = json.loads(cleaned)
        return parsed if isinstance(parsed, list) else []
    except Exception as e:
        print(f"[extract_actions] LLM call failed: {e}", flush=True)
        return []
