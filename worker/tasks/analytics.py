"""
Analytics computation task — meeting health score, engagement, talk time.
"""
from sqlalchemy import text
from db import get_session


def compute_analytics(meeting_id: str, segments: list[dict], summary: dict):
    """Compute all analytics and write to meeting_analytics table."""
    if not segments:
        return

    # ── Talk time per speaker ──────────────────────────────────────────────
    talk_time: dict[str, float] = {}
    word_count = 0
    questions_count = 0

    for seg in segments:
        speaker = seg.get("speaker_name", "Unknown")
        dur = (seg.get("duration_ms") or (seg.get("end_ms", 0) - seg.get("start_ms", 0))) / 1000.0
        talk_time[speaker] = talk_time.get(speaker, 0) + dur
        text_val = seg.get("text", "")
        word_count += len(text_val.split())
        if "?" in text_val:
            questions_count += 1

    total_talk = sum(talk_time.values()) or 1.0

    # ── Engagement score (0-100) ───────────────────────────────────────────
    # Based on: participant balance, question density, word density
    num_speakers = len(talk_time)
    if num_speakers > 1:
        # Gini-coefficient-like balance (1.0 = perfectly equal)
        shares = [v / total_talk for v in talk_time.values()]
        max_share = max(shares)
        balance = 1.0 - (max_share - 1 / num_speakers) * num_speakers / (num_speakers - 1)
        balance = max(0.0, min(1.0, balance))
    else:
        balance = 0.5

    words_per_min = word_count / (total_talk / 60) if total_talk > 0 else 0
    density_score = min(1.0, words_per_min / 150)  # 150 wpm = perfect density

    q_per_min = questions_count / (total_talk / 60) if total_talk > 0 else 0
    question_score = min(1.0, q_per_min / 2.0)  # 2 questions per minute = perfect

    engagement_score = int(round((balance * 0.4 + density_score * 0.4 + question_score * 0.2) * 100))

    # ── Health score (0-100) ───────────────────────────────────────────────
    decisions_count = len(summary.get("decisions") or [])
    next_steps_count = len(summary.get("next_steps") or [])
    risks_count = len(summary.get("risks") or [])
    sentiment = summary.get("sentiment", "")
    sentiment_bonus = {
        "productive": 20, "informational": 10, "follow-up-needed": 5,
        "inconclusive": -10, "urgent": 0,
    }.get(sentiment, 0)

    health_score = (
        engagement_score * 0.5
        + min(decisions_count * 8, 20)
        + min(next_steps_count * 5, 20)
        - min(risks_count * 5, 15)
        + sentiment_bonus
    )
    health_score = max(0, min(100, int(round(health_score))))

    # ── Sentiment timeline ──────────────────────────────────────────────────
    # Simple minute-by-minute word count as proxy for engagement
    timeline_buckets: dict[int, int] = {}
    for seg in segments:
        start_ms = seg.get("start_ms", 0)
        minute = start_ms // 60000
        timeline_buckets[minute] = timeline_buckets.get(minute, 0) + len(seg.get("text", "").split())

    sentiment_timeline = [
        {"minute": m, "words": w}
        for m, w in sorted(timeline_buckets.items())
    ]

    # ── Persist ────────────────────────────────────────────────────────────
    with get_session() as session:
        import json

        session.execute(
            text("""
                UPDATE meetings
                SET health_score = :health_score,
                    engagement_score = :engagement_score,
                    sentiment = COALESCE(NULLIF(sentiment, ''), :sentiment)
                WHERE id = :id
            """),
            {
                "health_score": health_score,
                "engagement_score": engagement_score,
                "sentiment": sentiment,
                "id": meeting_id,
            },
        )

        session.execute(
            text("""
                INSERT INTO meeting_analytics
                    (id, meeting_id, engagement_score, health_score, sentiment_score,
                     sentiment_timeline, talk_time_per_speaker,
                     decisions_count, questions_count, word_count)
                VALUES
                    (gen_random_uuid(), :meeting_id, :engagement, :health, :sentiment_score,
                     :sentiment_timeline::jsonb, :talk_time::jsonb,
                     :decisions, :questions, :words)
                ON CONFLICT (meeting_id)
                DO UPDATE SET
                    engagement_score = EXCLUDED.engagement_score,
                    health_score = EXCLUDED.health_score,
                    sentiment_score = EXCLUDED.sentiment_score,
                    sentiment_timeline = EXCLUDED.sentiment_timeline,
                    talk_time_per_speaker = EXCLUDED.talk_time_per_speaker,
                    decisions_count = EXCLUDED.decisions_count,
                    questions_count = EXCLUDED.questions_count,
                    word_count = EXCLUDED.word_count
            """),
            {
                "meeting_id": meeting_id,
                "engagement": engagement_score,
                "health": health_score,
                "sentiment_score": None,
                "sentiment_timeline": json.dumps(sentiment_timeline),
                "talk_time": json.dumps({k: round(v, 1) for k, v in talk_time.items()}),
                "decisions": decisions_count,
                "questions": questions_count,
                "words": word_count,
            },
        )
        session.commit()

    print(
        f"[analytics] {meeting_id}: health={health_score}, "
        f"engagement={engagement_score}, speakers={num_speakers}",
        flush=True,
    )
