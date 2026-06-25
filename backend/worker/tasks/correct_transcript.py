"""
Transcript correction via LLM — repairs ASR errors in code-switched text.
Ported from zapper/worker/tasks/correct_transcript.py.
"""
import os
from sqlalchemy import text
from db import get_session
from llm_client import chat_completion

TRANSCRIPT_LLM_CORRECT = os.getenv("TRANSCRIPT_LLM_CORRECT", "true").lower() == "true"
BATCH_SIZE = int(os.getenv("TRANSCRIPT_LLM_BATCH", "25"))
MAX_TOKENS = int(os.getenv("TRANSCRIPT_LLM_MAX_TOKENS", "4000"))

SYSTEM_PROMPT = """You are correcting ASR (speech recognition) output from a meeting.
The meeting may involve Hindi-English code-switching (Hinglish).
Fix ASR errors, mis-heard words, and grammatical issues.
Keep Hindi in Devanagari script, English/technical terms in Latin script.
Return ONLY the corrected text segments as a numbered list, one per line:
1. <corrected text>
2. <corrected text>
...
Do NOT add explanations. Preserve the speaker's meaning exactly."""


def correct_transcript(meeting_id: str, segments: list[dict]) -> list[dict]:
    """LLM-correct transcript segments in batches. Non-fatal — returns originals on failure."""
    if not TRANSCRIPT_LLM_CORRECT:
        print(f"[correct_transcript] LLM correction disabled — skipping", flush=True)
        return segments

    if not segments:
        return segments

    corrected_all = []
    for i in range(0, len(segments), BATCH_SIZE):
        batch = segments[i: i + BATCH_SIZE]
        try:
            corrected_batch = _correct_batch(batch)
            corrected_all.extend(corrected_batch)
        except Exception as e:
            print(f"[correct_transcript] Batch {i}…{i+BATCH_SIZE} failed (using original): {e}", flush=True)
            corrected_all.extend(batch)

    # Persist corrected text back to DB
    try:
        with get_session() as session:
            for seg in corrected_all:
                if seg.get("id") and seg.get("text"):
                    session.execute(
                        text("UPDATE transcript_segments SET text = :text WHERE id = :id"),
                        {"text": seg["text"], "id": seg["id"]},
                    )
            session.commit()
        print(f"[correct_transcript] Corrected {len(corrected_all)} segments for {meeting_id}", flush=True)
    except Exception as e:
        print(f"[correct_transcript] DB write failed (non-fatal): {e}", flush=True)

    return corrected_all


def _correct_batch(batch: list[dict]) -> list[dict]:
    numbered_input = "\n".join(f"{i+1}. {s.get('text', '')}" for i, s in enumerate(batch))
    raw = chat_completion(
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": f"Correct these ASR segments:\n\n{numbered_input}"},
        ],
        kind="mini",
        temperature=0.1,
        max_tokens=MAX_TOKENS,
    )

    result = list(batch)
    for line in raw.strip().splitlines():
        line = line.strip()
        if not line:
            continue
        import re
        m = re.match(r"^(\d+)\.\s+(.+)$", line)
        if m:
            idx = int(m.group(1)) - 1
            corrected_text = m.group(2).strip()
            if 0 <= idx < len(result):
                result[idx] = {**result[idx], "text": corrected_text}

    return result
