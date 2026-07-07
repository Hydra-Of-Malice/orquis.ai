"""
Post-meeting pipeline orchestrator.
Runs all AI processing tasks in sequence after a meeting ends.
"""
from celery_app import app
from sqlalchemy import text

from db import get_session


def _update_status(meeting_id: str, status: str, extra: dict = None):
    with get_session() as session:
        if extra:
            cols = ", ".join(f"{k} = :{k}" for k in extra.keys())
            params = {"id": meeting_id, "status": status, **extra}
            session.execute(
                text(f"UPDATE meetings SET status = :status, {cols} WHERE id = :id"),
                params,
            )
        else:
            session.execute(
                text("UPDATE meetings SET status = :status WHERE id = :id"),
                {"id": meeting_id, "status": status},
            )
        session.commit()


def _publish_ws_event(meeting_id: str, event_type: str, payload: dict = None):
    try:
        import redis
        import json
        import os
        redis_url = os.getenv("REDIS_URL", "redis://redis:6379/0")
        r = redis.from_url(redis_url)
        r.publish(
            f"zapper:live:{meeting_id}",
            json.dumps({"type": event_type, "payload": payload or {}})
        )
        r.close()
    except Exception as e:
        print(f"[pipeline] WS publish failed (non-fatal): {e}", flush=True)


@app.task(
    name="tasks.pipeline.run_post_meeting_pipeline",
    bind=True,
    max_retries=2,
    default_retry_delay=60,
)
def run_post_meeting_pipeline(self, meeting_id: str):
    """
    Orchestrates:
      1. Transcribe audio
      2. Correct transcript (LLM)
      3. Match speakers (voice fingerprinting)
      4. Summarise meeting
      5. Extract action items
      6. Compute analytics
      7. Embed transcript segments (pgvector)
      8. Upload to Azure Blob Storage
    """
    print(f"[pipeline] Starting post-meeting pipeline for {meeting_id}", flush=True)
    _publish_ws_event(meeting_id, "pipeline_started")

    try:
        # Step 1: Transcribe
        from tasks.transcribe import transcribe_recording
        segments = transcribe_recording(meeting_id)
        print(f"[pipeline] Transcription done — {len(segments)} segments", flush=True)
        _publish_ws_event(meeting_id, "transcribed", {"segment_count": len(segments)})

        if not segments:
            _update_status(meeting_id, "done")
            _publish_ws_event(meeting_id, "done")
            print(f"[pipeline] No segments — marking done for {meeting_id}", flush=True)
            return

        # Step 2: Correct transcript
        try:
            from tasks.correct_transcript import correct_transcript
            segments = correct_transcript(meeting_id, segments)
            print(f"[pipeline] Transcript correction done", flush=True)
        except Exception as e:
            print(f"[pipeline] WARN correct_transcript failed (non-fatal): {e}", flush=True)

        # Step 3: Match speakers
        try:
            from tasks.match_speakers import match_speakers
            segments = match_speakers(meeting_id, segments)
            print(f"[pipeline] Speaker matching done", flush=True)
        except Exception as e:
            print(f"[pipeline] WARN match_speakers failed (non-fatal): {e}", flush=True)

        # Step 4: Summarise
        try:
            from tasks.summarise import summarise_recording
            summary = summarise_recording(meeting_id, segments)
            print(f"[pipeline] Summarisation done", flush=True)
            _publish_ws_event(meeting_id, "summarised")
        except Exception as e:
            print(f"[pipeline] WARN summarise failed (non-fatal): {e}", flush=True)
            summary = {}

        # Step 5: Extract action items
        try:
            from tasks.extract_actions import extract_actions
            extract_actions(meeting_id, segments)
            print(f"[pipeline] Action items extracted", flush=True)
        except Exception as e:
            print(f"[pipeline] WARN extract_actions failed (non-fatal): {e}", flush=True)

        # Step 6: Compute analytics
        try:
            from tasks.analytics import compute_analytics
            compute_analytics(meeting_id, segments, summary)
            print(f"[pipeline] Analytics computed", flush=True)
        except Exception as e:
            print(f"[pipeline] WARN compute_analytics failed (non-fatal): {e}", flush=True)

        # Step 7: Embed segments (async via separate task)
        try:
            from tasks.embed_segments import embed_segments
            embed_segments.delay(meeting_id)
            print(f"[pipeline] Embedding task queued", flush=True)
        except Exception as e:
            print(f"[pipeline] WARN embed_segments queue failed (non-fatal): {e}", flush=True)

        # Step 8: Azure upload (async via separate task)
        try:
            from tasks.azure_storage import upload_meeting_assets
            import os
            if os.getenv("AZURE_STORAGE_CONNECTION_STRING"):
                upload_meeting_assets.delay(meeting_id)
                print(f"[pipeline] Azure upload task queued", flush=True)
        except Exception as e:
            print(f"[pipeline] WARN azure_upload queue failed (non-fatal): {e}", flush=True)

        _update_status(meeting_id, "done")
        _publish_ws_event(meeting_id, "done")
        print(f"[pipeline] Pipeline complete for {meeting_id}", flush=True)

        # Step 9: Execute automations (Jira, Linear, Slack, etc.)
        try:
            import asyncio
            from app.routers.automations import execute_automations
            with get_session() as session:
                meeting_row = session.execute(
                    text("SELECT org_id, title, summary_md, duration_seconds FROM meetings WHERE id = :id"),
                    {"id": meeting_id},
                ).fetchone()
                action_rows = session.execute(
                    text("SELECT id, title, description, assignee_name, priority, jira_id, linear_id FROM action_items WHERE meeting_id = :id"),
                    {"id": meeting_id},
                ).fetchall()

            if meeting_row:
                org_id = str(meeting_row[0])
                context = {
                    "meeting_id": meeting_id,
                    "meeting_title": meeting_row[1] or "Meeting",
                    "summary_md": meeting_row[2] or "",
                    "duration_seconds": meeting_row[3] or 0,
                    "action_items": [
                        {
                            "id": str(r[0]),
                            "title": r[1],
                            "description": r[2] or "",
                            "assignee_name": r[3] or "",
                            "priority": r[4] or "medium",
                            "jira_id": r[5],
                            "linear_id": r[6],
                        }
                        for r in action_rows
                    ],
                }
                asyncio.run(execute_automations("meeting.ended", org_id, context))
                print(f"[pipeline] Automations executed for {meeting_id}", flush=True)
        except Exception as exc:
            print(f"[pipeline] WARN automations failed (non-fatal): {exc}", flush=True)

    except Exception as exc:
        print(f"[pipeline] FATAL error for {meeting_id}: {exc}", flush=True)
        _update_status(meeting_id, "error")
        _publish_ws_event(meeting_id, "error", {"message": str(exc)})
        raise self.retry(exc=exc)
