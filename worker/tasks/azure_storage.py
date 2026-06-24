"""
Azure Blob Storage upload task.
Uploads audio, per-track WAVs, screenshots, and video after meeting completion.
"""
import glob
import json
import os

from celery_app import app
from sqlalchemy import text
from db import get_session

STORAGE_PATH = os.getenv("STORAGE_PATH", "/data/recordings")
AZURE_CONTAINER = os.getenv("AZURE_STORAGE_CONTAINER", "recordings")


def _get_blob_client():
    conn_str = os.getenv("AZURE_STORAGE_CONNECTION_STRING", "")
    if not conn_str:
        raise ValueError("AZURE_STORAGE_CONNECTION_STRING not set")
    from azure.storage.blob import BlobServiceClient
    return BlobServiceClient.from_connection_string(conn_str)


def _upload_file(local_path: str, blob_name: str, content_type: str = "application/octet-stream") -> str:
    client = _get_blob_client()
    cc = client.get_blob_client(container=AZURE_CONTAINER, blob=blob_name)
    with open(local_path, "rb") as f:
        cc.upload_blob(f, overwrite=True, content_settings={"content_type": content_type})
    account = client.account_name
    return f"https://{account}.blob.core.windows.net/{AZURE_CONTAINER}/{blob_name}"


@app.task(name="tasks.azure_storage.upload_meeting_assets", bind=True, max_retries=3, default_retry_delay=300)
def upload_meeting_assets(self, meeting_id: str):
    """Upload all audio/video/screenshot assets to Azure Blob Storage."""
    try:
        with get_session() as session:
            row = session.execute(
                text("SELECT wav_path, video_path FROM meetings WHERE id = :id"),
                {"id": meeting_id},
            ).fetchone()

        if not row:
            return

        wav_path, video_path = row
        updates = {}

        if wav_path and os.path.isfile(wav_path) and not wav_path.startswith("http"):
            blob_name = f"{meeting_id}/audio.wav"
            blob_url = _upload_file(wav_path, blob_name, "audio/wav")
            updates["wav_path"] = blob_url
            print(f"[azure_storage] Uploaded audio for {meeting_id}: {blob_url}", flush=True)

        if video_path and os.path.isfile(video_path) and not video_path.startswith("http"):
            blob_name = f"{meeting_id}/screen.mp4"
            blob_url = _upload_file(video_path, blob_name, "video/mp4")
            updates["video_path"] = blob_url
            print(f"[azure_storage] Uploaded video for {meeting_id}: {blob_url}", flush=True)

        # Per-track WAVs
        rec_dir = os.path.dirname(wav_path) if wav_path and not wav_path.startswith("http") else ""
        if rec_dir and os.path.isdir(rec_dir):
            for track_wav in glob.glob(os.path.join(rec_dir, "audio_js_t*.wav")):
                basename = os.path.basename(track_wav)
                blob_name = f"{meeting_id}/{basename}"
                _upload_file(track_wav, blob_name, "audio/wav")
                print(f"[azure_storage] Uploaded track {basename}", flush=True)

            for screenshot in glob.glob(os.path.join(rec_dir, "screenshot_*.png")):
                basename = os.path.basename(screenshot)
                blob_name = f"{meeting_id}/screenshots/{basename}"
                _upload_file(screenshot, blob_name, "image/png")

        if updates:
            set_clause = ", ".join(f"{k} = :{k}" for k in updates.keys())
            with get_session() as session:
                session.execute(
                    text(f"UPDATE meetings SET {set_clause} WHERE id = :id"),
                    {**updates, "id": meeting_id},
                )
                session.commit()

        print(f"[azure_storage] Upload complete for {meeting_id}", flush=True)

    except Exception as exc:
        print(f"[azure_storage] Upload failed for {meeting_id}: {exc}", flush=True)
        raise self.retry(exc=exc)


@app.task(name="tasks.azure_storage.upload_video")
def upload_video(meeting_id: str, video_path: str):
    """Upload a specific video file to Azure Blob."""
    if not video_path or not os.path.isfile(video_path):
        return
    blob_name = f"{meeting_id}/screen.mp4"
    blob_url = _upload_file(video_path, blob_name, "video/mp4")
    with get_session() as session:
        session.execute(
            text("UPDATE meetings SET video_path = :url WHERE id = :id"),
            {"url": blob_url, "id": meeting_id},
        )
        session.commit()
    print(f"[azure_storage] Video uploaded: {blob_url}", flush=True)
