"""
Celery tasks for AI and background jobs.
AI queue: enqueue Claude analysis for fair scheduling under load.
"""

import json
import logging
import os

from workers.celery_app import app

logger = logging.getLogger("claudebot.ai_tasks")

AI_STATE_TTL = 300  # 5 min


def _get_redis():
    """Get Redis client for state storage."""
    import redis

    url = os.getenv("REDIS_URL", "").strip()
    if not url:
        return None
    try:
        return redis.from_url(url, decode_responses=True)
    except Exception as e:
        logger.warning("Redis unavailable for AI state: %s", e)
        return None


@app.task(bind=True, max_retries=3)
def run_ai_analysis(self, task_id: str, skip_scout: bool = False):
    """
    Run Claude AI analysis from state in Redis. Publishes result to ai:result channel.
    Backend writes state to ai:state:{task_id} before enqueue; subscribes to ai:result for result.
    """
    r = _get_redis()
    if not r:
        logger.error("Redis required for Celery AI — cannot run")
        return {"status": "error", "error": "Redis unavailable"}

    state_key = f"ai:state:{task_id}"
    raw = r.get(state_key)
    if not raw:
        logger.warning("No state found for task %s — may have expired", task_id[:8])
        return {"status": "error", "error": "State expired"}

    try:
        state = json.loads(raw)
    except json.JSONDecodeError as e:
        logger.error("Invalid state JSON for %s: %s", task_id[:8], e)
        return {"status": "error", "error": "Invalid state"}

    user_id = state.get("user_id", "default")
    try:
        from ai.celery_ai_runner import run_ai_analysis_sync

        decision = run_ai_analysis_sync(state, skip_scout=skip_scout)
    except Exception as e:
        logger.exception("AI analysis failed for %s", task_id[:8])
        r.delete(state_key)
        from core.redis_client import ai_pending_decrement

        ai_pending_decrement(user_id)
        raise self.retry(exc=e) from e

    r.delete(state_key)

    from ai.claude_ai import get_cost_tracker
    from core.redis_client import ai_pending_decrement

    ai_pending_decrement(user_id)

    result = {
        "task_id": task_id,
        "decision": decision,
        "cost_tracker": get_cost_tracker(),
    }
    r.publish("ai:result", json.dumps(result, default=str))
    logger.info("AI result published for task %s", task_id[:8])
    return {"status": "ok", "task_id": task_id}


@app.task
def health_check():
    """Simple health check for worker monitoring."""
    return {"ok": True}
