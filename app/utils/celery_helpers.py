from typing import Optional, Dict, Any, List
from datetime import datetime, timezone
import logging
import redis.asyncio as aioredis

from app.celery_config import celery_app
from app.core.redis_keys import redis_key
from config import settings

logger = logging.getLogger(__name__)


async def get_celery_status() -> Dict[str, Any]:
    try:
        # Check if workers are active
        inspect = celery_app.control.inspect()

        active_workers = inspect.active()
        scheduled_tasks = inspect.scheduled()
        registered_tasks = inspect.registered()

        # Get active task count
        active_count = 0
        if active_workers:
            for worker, tasks in active_workers.items():
                active_count += len(tasks)

        # Get scheduled task count
        scheduled_count = 0
        if scheduled_tasks:
            for worker, tasks in scheduled_tasks.items():
                scheduled_count += len(tasks)

        return {
            'enabled': settings.ENABLE_NEWS_SCHEDULER,
            'workers': {
                'active': len(active_workers) if active_workers else 0,
                'workers': list(active_workers.keys()) if active_workers else []
            },
            'tasks': {
                'active': active_count,
                'scheduled': scheduled_count,
                'registered': list(registered_tasks.values())[0] if registered_tasks else []
            },
            'beat_schedule': {
                task_name: {
                    'schedule': str(task_config['schedule']),
                    'task': task_config['task']
                }
                for task_name, task_config in celery_app.conf.beat_schedule.items()
            }
        }
    except Exception as e:
        logger.error(f"Error getting Celery status: {e}")
        return {
            'enabled': settings.ENABLE_NEWS_SCHEDULER,
            'error': str(e),
            'message': 'Celery worker may not be running'
        }


async def get_last_fetch_time(redis_client: aioredis.Redis) -> Optional[datetime]:
    """Get timestamp of last successful fetch from Redis"""
    try:
        timestamp = await redis_client.get(redis_key("news", "last_fetch_timestamp"))
        if timestamp:
            if isinstance(timestamp, bytes):
                timestamp = timestamp.decode('utf-8')
            return datetime.fromisoformat(timestamp)
        return None
    except Exception as e:
        logger.error(f"Error getting last fetch time: {e}")
        return None


def _normalize_timestamp(raw_timestamp: Any) -> Optional[datetime]:
    if not raw_timestamp:
        return None
    if isinstance(raw_timestamp, bytes):
        raw_timestamp = raw_timestamp.decode("utf-8")
    try:
        return datetime.fromisoformat(str(raw_timestamp))
    except Exception:
        return None


def _heartbeat_entry(last_seen: Optional[datetime], now: datetime, ttl_seconds: int) -> Dict[str, Any]:
    if not last_seen:
        return {"status": "missing", "last_seen": None, "age_seconds": None}

    age_seconds = max(0, int((now - last_seen).total_seconds()))
    if age_seconds > ttl_seconds:
        status = "stale"
    else:
        status = "fresh"
    return {"status": status, "last_seen": last_seen.isoformat(), "age_seconds": age_seconds}


async def get_celery_runtime_heartbeat(redis_client: aioredis.Redis) -> Dict[str, Any]:
    try:
        beat_key = redis_key("celery", "heartbeat", "beat")
        worker_key = redis_key("celery", "heartbeat", "worker", "latest")
        beat_raw, worker_raw = await redis_client.mget(beat_key, worker_key)

        now = datetime.now(timezone.utc)
        ttl_seconds = max(settings.CELERY_HEARTBEAT_TTL_SECONDS, settings.CELERY_HEARTBEAT_INTERVAL_SECONDS * 2)
        beat_entry = _heartbeat_entry(_normalize_timestamp(beat_raw), now, ttl_seconds)
        worker_entry = _heartbeat_entry(_normalize_timestamp(worker_raw), now, ttl_seconds)

        healthy = beat_entry["status"] == "fresh" and worker_entry["status"] == "fresh"
        return {
            "healthy": healthy,
            "interval_seconds": settings.CELERY_HEARTBEAT_INTERVAL_SECONDS,
            "ttl_seconds": ttl_seconds,
            "beat": beat_entry,
            "worker": worker_entry,
        }
    except Exception as e:
        logger.error(f"Error getting Celery runtime heartbeat: {e}")
        ttl_seconds = max(settings.CELERY_HEARTBEAT_TTL_SECONDS, settings.CELERY_HEARTBEAT_INTERVAL_SECONDS * 2)
        return {
            "healthy": False,
            "error": str(e),
            "interval_seconds": settings.CELERY_HEARTBEAT_INTERVAL_SECONDS,
            "ttl_seconds": ttl_seconds,
            "beat": {"status": "unknown", "last_seen": None, "age_seconds": None},
            "worker": {"status": "unknown", "last_seen": None, "age_seconds": None},
        }


async def trigger_manual_fetch(
    query: Optional[str] = None,
    queries: Optional[List[str]] = None,
    sources: Optional[List[str]] = None,
    limit: int = 50
) -> Dict[str, Any]:
    try:
        from app.tasks.news_tasks import fetch_news_manual, fetch_and_save_news

        normalized_queries = [q for q in (queries or []) if q]
        if query and query not in normalized_queries:
            normalized_queries.append(query)

        if len(normalized_queries) > 1:
            task = fetch_and_save_news.delay(normalized_queries, sources, limit)
        else:
            task_query = normalized_queries[0] if normalized_queries else query
            task = fetch_news_manual.delay(task_query, sources, limit)

        return {
            'success': True,
            'task_id': task.id,
            'status': 'queued',
            'message': 'News fetch task queued successfully'
        }
    except Exception as e:
        logger.error(f"Error triggering manual fetch: {e}", exc_info=True)
        return {
            'success': False,
            'error': 'Failed to queue news fetch task'
        }


async def get_task_status(task_id: str) -> Dict[str, Any]:
    try:
        from celery.result import AsyncResult

        result = AsyncResult(task_id, app=celery_app)

        response = {
            'task_id': task_id,
            'status': result.status,
            'ready': result.ready(),
            'successful': result.successful() if result.ready() else None
        }

        if result.ready():
            if result.successful():
                response['result'] = result.result
            else:
                logger.error(f"Task {task_id} failed: {result.info}")
                response['error'] = 'Task failed'

        return response
    except Exception as e:
        logger.error(f"Error getting task status: {e}")
        return {
            'task_id': task_id,
            'error': 'Failed to retrieve task status'
        }


async def revoke_task(task_id: str, terminate: bool = False) -> Dict[str, Any]:
    try:
        celery_app.control.revoke(task_id, terminate=terminate)

        return {
            'success': True,
            'task_id': task_id,
            'message': f'Task {"terminated" if terminate else "revoked"} successfully'
        }
    except Exception as e:
        logger.error(f"Error revoking task: {e}")
        return {
            'success': False,
            'task_id': task_id,
            'error': 'Failed to revoke task'
        }


def get_scheduled_tasks_info() -> Dict[str, Any]:
    """Get information about scheduled periodic tasks"""
    return {
        'beat_schedule': {
            task_name: {
                'task': task_config['task'],
                'schedule': str(task_config['schedule']),
                'options': task_config.get('options', {})
            }
            for task_name, task_config in celery_app.conf.beat_schedule.items()
        },
        'timezone': str(celery_app.conf.timezone),
        'enabled': settings.ENABLE_NEWS_SCHEDULER
    }

