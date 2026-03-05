"""
Celery app for 10k scale — background jobs, AI queue (future).
Uses Redis as broker. Run: celery -A workers.celery_app worker -l info
"""

import os

from celery import Celery

REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")

app = Celery(
    "claudebot",
    broker=REDIS_URL,
    backend=REDIS_URL,
    include=["workers.ai_tasks"],
)

app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
    task_default_queue="default",
    task_routes={
        "workers.ai_tasks.run_ai_analysis": {"queue": "ai"},
    },
    task_acks_late=True,
    worker_prefetch_multiplier=1,
)
