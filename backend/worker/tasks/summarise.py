"""
Summarization task — two-tier structured summary via LLM.
Ported from zapper/worker/tasks/summarise.py — no external dependency.
"""
import json
import re

from sqlalchemy import text
from db import get_session
from llm_client import chat_completion_json, chat_completion


SYSTEM_PROMPT = """You are a meeting intelligence assistant that analyzes meeting transcripts and generates structured summaries.

Your response is a JSON object with these fields:

{
  "title": "the meeting topic or name, around 5-10 words",
  "short_summary": "a brief 1-3 sentence description of the meeting purpose and outcome",
  "overview": "a multi-paragraph narrative describing what happened during the meeting in chronological order",
  "key_topics": [
    {
      "topic": "topic name",
      "detail": "description of what was discussed about this topic and its outcome"
    }
  ],
  "decisions": ["list of decisions made during the meeting"],
  "next_steps": [
    {
      "task": "action item description",
      "owner": "person assigned to this task, or null",
      "due": "deadline if mentioned, or null"
    }
  ],
  "risks": ["any risks or blockers mentioned"],
  "questions": ["any unresolved questions raised in the meeting"],
  "sentiment": "overall meeting outcome — one of: productive, inconclusive, follow-up-needed, informational, urgent",
  "chapter_markers": [
    {
      "label": "section or topic name",
      "start_minute": 0
    }
  ]
}"""


def summarise_recording(recording_id: str, segments: list[dict]) -> dict:
    """Generate a structured summary and persist to the meetings table."""
    transcript = _build_transcript(segments)
    if not transcript.strip():
        return {}

    summary = _call_llm(transcript)
    if not summary:
        return {}

    summary_md = _to_markdown(summary)
    sentiment = summary.get("sentiment", "")

    with get_session() as session:
        session.execute(
            text("""
                UPDATE meetings
                SET summary_md = :summary_md,
                    summary_json = :summary_json,
                    sentiment = :sentiment,
                    title = COALESCE(NULLIF(title, ''), :title, title)
                WHERE id = :id
            """),
            {
                "summary_md": summary_md,
                "summary_json": json.dumps(summary),
                "sentiment": sentiment,
                "title": summary.get("title") or "Untitled Meeting",
                "id": recording_id,
            },
        )
        session.commit()

    return summary


def _build_transcript(segments: list[dict]) -> str:
    lines = []
    for s in segments:
        if not s.get("text"):
            continue
        start_ms = s.get("offset_ms", 0) or s.get("start_ms", 0)
        start_min = start_ms // 60000
        start_sec = (start_ms % 60000) // 1000
        ts = f"[{start_min:02d}:{start_sec:02d}]"
        speaker = s.get("speaker_name", "Unknown")
        lines.append(f"{ts} {speaker}: {s['text']}")
    return "\n".join(lines)


def _safe_json_loads(raw: str) -> dict:
    cleaned = re.sub(r"```(?:json)?\s*|\s*```", "", raw).strip()
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        pass

    def _fix_string(m: re.Match) -> str:
        content = m.group(0)
        content = content.replace("\r\n", "\\n").replace("\r", "\\n").replace("\n", "\\n")
        content = content.replace("\t", "\\t")
        return content

    sanitized = re.sub(r'"(?:[^"\\]|\\.)*"', _fix_string, cleaned, flags=re.DOTALL)
    try:
        return json.loads(sanitized)
    except json.JSONDecodeError as exc:
        print(f"[summarise] _safe_json_loads failed: {exc}", flush=True)
        return {}


def _call_llm(transcript: str) -> dict:
    try:
        return chat_completion_json(
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {
                    "role": "user",
                    "content": (
                        "Here is the meeting transcript. Produce a structured summary in JSON format.\n\n"
                        "TRANSCRIPT:\n" + transcript
                    ),
                },
            ],
            kind="main",
            temperature=0.2,
            max_tokens=4000,
        )
    except (json.JSONDecodeError, Exception) as exc:
        print(f"[summarise] JSON mode failed ({exc}), retrying with raw text…", flush=True)
        try:
            raw = chat_completion(
                messages=[
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {
                        "role": "user",
                        "content": (
                            "Produce a meeting summary for the transcript below.\n\n"
                            "TRANSCRIPT:\n" + transcript
                        ),
                    },
                ],
                kind="main",
                temperature=0.2,
                max_tokens=4000,
            )
            return _safe_json_loads(raw)
        except Exception as e2:
            print(f"[summarise] LLM call failed: {e2}", flush=True)
            return {}


def _to_markdown(summary: dict) -> str:
    lines: list[str] = []
    title = summary.get("title", "Meeting Summary")
    lines.append(f"# {title}\n")

    if short := summary.get("short_summary"):
        lines.append(f"> {short}\n")

    sentiment = summary.get("sentiment", "")
    if sentiment:
        emoji = {
            "productive": "✅", "inconclusive": "⚠️",
            "follow-up-needed": "🔄", "informational": "ℹ️", "urgent": "🚨",
        }.get(sentiment, "")
        lines.append(f"**Sentiment:** {emoji} {sentiment.replace('-', ' ').title()}\n")

    if overview := summary.get("overview"):
        lines.append("## Overview\n")
        lines.append(f"{overview}\n")

    if chapters := summary.get("chapter_markers"):
        lines.append("## Chapter Markers\n")
        for ch in chapters:
            m = ch.get("start_minute", 0)
            label = ch.get("label", "")
            lines.append(f"- **{m:02d}:00** — {label}")
        lines.append("")

    if kt := summary.get("key_topics"):
        lines.append("## Key Topics\n")
        for t in kt:
            if isinstance(t, dict):
                lines.append(f"**{t.get('topic', '')}**")
                if detail := t.get("detail"):
                    lines.append(f"{detail}\n")
        lines.append("")

    if decisions := summary.get("decisions"):
        lines.append("## Decisions\n")
        for d in decisions:
            lines.append(f"- {d}")
        lines.append("")

    if ns := summary.get("next_steps"):
        lines.append("## Next Steps\n")
        for n in ns:
            if isinstance(n, dict):
                task = n.get("task", "")
                owner = n.get("owner")
                due = n.get("due")
                suffix = ""
                if owner:
                    suffix += f" · **{owner}**"
                if due:
                    suffix += f" · {due}"
                lines.append(f"- {task}{suffix}")
            else:
                lines.append(f"- {n}")
        lines.append("")

    if risks := summary.get("risks"):
        lines.append("## Risks & Blockers\n")
        for r in risks:
            lines.append(f"- ⚠️ {r}")
        lines.append("")

    if questions := summary.get("questions"):
        lines.append("## Open Questions\n")
        for q in questions:
            lines.append(f"- ❓ {q}")
        lines.append("")

    return "\n".join(lines)
