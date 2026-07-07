"""
Celery client for the FastAPI backend.
Allows the backend to dispatch Celery tasks without importing the worker.
"""
from celery import Celery
import os

REDIS_URL = os.getenv("REDIS_URL", "redis://redis:6379/0")

_app = Celery(broker=REDIS_URL, backend=REDIS_URL)
_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
    task_routes={
        "tasks.pipeline.*": {"queue": "transcription"},
        "tasks.summarise.*": {"queue": "analysis"},
        "tasks.embed_segments.*": {"queue": "analysis"},
        "tasks.azure_storage.*": {"queue": "analysis"},
    },
)


class _Task:
    def __init__(self, task_name: str, queue: str | None = None):
        self.task_name = task_name
        self.queue = queue

    def delay(self, *args, **kwargs):
        return _app.send_task(self.task_name, args=args, kwargs=kwargs, queue=self.queue)

    def apply_async(self, args=None, kwargs=None, **options):
        if "queue" not in options and self.queue:
            options["queue"] = self.queue
        return _app.send_task(self.task_name, args=args, kwargs=kwargs, **options)


# ── Task stubs (dispatched by name to worker) ─────────────────────────────────
run_post_meeting_pipeline = _Task("tasks.pipeline.run_post_meeting_pipeline", queue="transcription")
summarise_meeting = _Task("tasks.summarise.summarise_recording", queue="analysis")
embed_segments = _Task("tasks.embed_segments.embed_segments", queue="analysis")
upload_video = _Task("tasks.azure_storage.upload_video", queue="analysis")
upload_meeting_assets = _Task("tasks.azure_storage.upload_meeting_assets", queue="analysis")
