"""
Celery application — broker/backend via Redis.
"""
import os
from celery import Celery

REDIS_URL = os.getenv("REDIS_URL", "redis://redis:6379/0")

app = Celery(
    "zapper_pm_worker",
    broker=REDIS_URL,
    backend=REDIS_URL,
    include=[
        "tasks.pipeline",
        "tasks.transcribe",
        "tasks.match_speakers",
        "tasks.summarise",
        "tasks.extract_actions",
        "tasks.analytics",
        "tasks.embed_segments",
        "tasks.correct_transcript",
        "tasks.azure_storage",
    ],
)

app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
    task_acks_late=True,
    task_reject_on_worker_lost=True,
    worker_prefetch_multiplier=1,
    task_routes={
        "tasks.transcribe.*": {"queue": "transcription"},
        "tasks.pipeline.*": {"queue": "transcription"},
        "tasks.summarise.*": {"queue": "analysis"},
        "tasks.extract_actions.*": {"queue": "analysis"},
        "tasks.analytics.*": {"queue": "analysis"},
        "tasks.embed_segments.*": {"queue": "analysis"},
        "tasks.correct_transcript.*": {"queue": "transcription"},
        "tasks.azure_storage.*": {"queue": "analysis"},
    },
)

celery_app = app
