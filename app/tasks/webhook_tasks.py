from __future__ import annotations

import asyncio
from datetime import datetime, timezone
import secrets
from typing import Dict, Optional, Tuple
from uuid import UUID

import redis.asyncio as aioredis
from sqlalchemy import select
import logging

from app.celery_config import celery_app
from app.core.redis_keys import redis_key
from app.models.article import Article
from app.models.integration import WebhookDeliveryItem, WebhookDeliveryJob, UserWebhook
from app.services.api_key_service import api_key_service
from app.services.delivery_planner_service import delivery_planner_service
from app.services.feed_service import feed_service
from app.services.webhook_service import webhook_service
from config import settings

logger = logging.getLogger(__name__)
PLANNER_LOCK_KEY = redis_key("integration", "webhook", "planner", "lock")
PLANNER_LOCK_TTL_SECONDS = 240


async def _acquire_planner_lock() -> Tuple[Optional[aioredis.Redis], Optional[str], bool]:
    try:
        redis_client = aioredis.from_url(
            settings.REDIS_URL,
            encoding="utf-8",
            decode_responses=True,
            max_connections=5,
        )
        token = secrets.token_hex(16)
        acquired = await redis_client.set(PLANNER_LOCK_KEY, token, ex=PLANNER_LOCK_TTL_SECONDS, nx=True)
        if acquired:
            return redis_client, token, True
        await redis_client.close()
        return None, None, False
    except Exception as exc:
        logger.warning("Planner lock unavailable, skipping planner run: %s", exc)
        return None, None, False


async def _release_planner_lock(redis_client: aioredis.Redis, token: str) -> None:
    try:
        await redis_client.eval(
            "if redis.call('get', KEYS[1]) == ARGV[1] then "
            "return redis.call('del', KEYS[1]) else return 0 end",
            1,
            PLANNER_LOCK_KEY,
            token,
        )
    except Exception as exc:
        logger.warning("Failed to release planner lock: %s", exc)
    finally:
        await redis_client.close()


@celery_app.task(
    name="app.tasks.webhook_tasks.plan_webhook_batches",
    bind=True,
    autoretry_for=(Exception,),
    retry_kwargs={"max_retries": 3, "countdown": 60},
)
def plan_webhook_batches(self):
    return asyncio.run(_async_plan_webhook_batches())


async def _async_plan_webhook_batches() -> Dict[str, int]:
    if not settings.ENABLE_INTEGRATION_API or not settings.ENABLE_INTEGRATION_DELIVERY:
        return {"queued_jobs": 0, "due_webhooks": 0}

    lock_client: Optional[aioredis.Redis] = None
    lock_token: Optional[str] = None
    lock_client, lock_token, should_run = await _acquire_planner_lock()
    if not should_run:
        logger.info("Skipping webhook planner run because another planner instance holds the lock")
        return {"queued_jobs": 0, "due_webhooks": 0}

    from app.core.database import create_task_session

    queued_jobs = 0
    due_count = 0
    try:
        async with create_task_session() as db:
            due_webhooks = await delivery_planner_service.get_due_webhooks(db=db)
            due_count = len(due_webhooks)

            for webhook in due_webhooks:
                items, window_start, window_end = await delivery_planner_service.compute_webhook_batch_items(
                    webhook=webhook,
                    db=db,
                )
                if not items:
                    webhook.last_attempted_at = datetime.now(timezone.utc)
                    await db.commit()
                    continue

                job = await delivery_planner_service.create_delivery_job(
                    webhook=webhook,
                    items=items,
                    window_start=window_start,
                    window_end=window_end,
                    db=db,
                )
                if not job:
                    continue

                queued_jobs += 1
                deliver_webhook_batch.delay(str(job.job_id))
    finally:
        if lock_client and lock_token:
            await _release_planner_lock(lock_client, lock_token)

    logger.info("Planned %s webhook delivery jobs from %s due webhooks", queued_jobs, due_count)
    return {"queued_jobs": queued_jobs, "due_webhooks": due_count}


@celery_app.task(
    name="app.tasks.webhook_tasks.deliver_webhook_batch",
    bind=True,
    autoretry_for=(Exception,),
    retry_kwargs={"max_retries": 3, "countdown": 60},
)
def deliver_webhook_batch(self, job_id: str):
    return asyncio.run(_async_deliver_webhook_batch(job_id))


async def _async_deliver_webhook_batch(job_id: str) -> Dict[str, str]:
    if not settings.ENABLE_INTEGRATION_API or not settings.ENABLE_INTEGRATION_DELIVERY:
        return {"status": "skipped"}

    from app.core.database import create_task_session

    async with create_task_session() as db:
        try:
            job_uuid = UUID(job_id)
        except ValueError:
            return {"status": "invalid_job_id"}

        job_result = await db.execute(
            select(WebhookDeliveryJob).where(WebhookDeliveryJob.job_id == job_uuid)
        )
        job = job_result.scalar_one_or_none()
        if not job:
            return {"status": "job_not_found"}

        if job.status in {"delivered", "cancelled", "dead_letter"}:
            return {"status": "already_terminal"}

        webhook_result = await db.execute(
            select(UserWebhook).where(UserWebhook.webhook_id == job.webhook_id)
        )
        webhook = webhook_result.scalar_one_or_none()
        if not webhook or not webhook.is_active:
            job.status = "cancelled"
            job.updated_at = datetime.now(timezone.utc)
            await db.commit()
            return {"status": "webhook_inactive"}

        job.status = "processing"
        job.updated_at = datetime.now(timezone.utc)
        await db.commit()

        item_result = await db.execute(
            select(WebhookDeliveryItem, Article)
            .join(Article, Article.article_id == WebhookDeliveryItem.article_id)
            .where(WebhookDeliveryItem.job_id == job.job_id)
            .order_by(WebhookDeliveryItem.position.asc())
        )
        rows = item_result.all()
        items = []
        for row_item, article in rows:
            items.append(
                {
                    "article_id": str(article.article_id),
                    "title": article.title,
                    "url": article.url,
                    "source_name": article.source_name,
                    "published_date": article.published_date.isoformat() if article.published_date else None,
                    "topics": article.topics or [],
                }
            )

        if webhook.feed_id:
            source = await feed_service.get_feed(feed_id=webhook.feed_id, user_id=webhook.user_id, db=db)
            source_id = source.feed_id if source else webhook.feed_id
            source_name = source.name if source else "Feed"
        else:
            source = await feed_service.get_bundle(bundle_id=webhook.bundle_id, user_id=webhook.user_id, db=db)
            source_id = source.bundle_id if source else webhook.bundle_id
            source_name = source.name if source else "Bundle"

        success, status_code, message = await webhook_service.deliver_webhook(
            webhook=webhook,
            source_id=source_id,
            source_name=source_name,
            items=items,
        )

        if success:
            latest_item = items[0] if items else None
            await delivery_planner_service.mark_job_success(
                job=job,
                webhook=webhook,
                latest_item=latest_item,
                db=db,
            )
            return {"status": "delivered", "http_status": str(status_code)}

        await delivery_planner_service.mark_job_failure(
            job=job,
            webhook=webhook,
            error=message,
            db=db,
        )
        return {"status": "failed", "http_status": str(status_code), "error": message}


@celery_app.task(
    name="app.tasks.webhook_tasks.flush_api_key_usage",
    bind=True,
    autoretry_for=(Exception,),
    retry_kwargs={"max_retries": 2, "countdown": 300},
)
def flush_api_key_usage(self):
    return asyncio.run(_async_flush_api_key_usage())


async def _async_flush_api_key_usage() -> Dict[str, int]:
    if not settings.ENABLE_INTEGRATION_API:
        return {"keys_processed": 0, "total_increment": 0}

    from app.core.database import create_task_session

    async with create_task_session() as db:
        result = await api_key_service.flush_usage_to_db(db=db)
        return result


@celery_app.task(
    name="app.tasks.webhook_tasks.cleanup_integration_delivery_history",
    bind=True,
    autoretry_for=(Exception,),
    retry_kwargs={"max_retries": 2, "countdown": 300},
)
def cleanup_integration_delivery_history(self):
    return asyncio.run(_async_cleanup_integration_delivery_history())


async def _async_cleanup_integration_delivery_history() -> Dict[str, int]:
    if not settings.ENABLE_INTEGRATION_API:
        return {"deleted_jobs": 0, "retention_days": int(settings.INTEGRATION_DELIVERY_RETENTION_DAYS)}

    from app.core.database import create_task_session

    async with create_task_session() as db:
        result = await delivery_planner_service.cleanup_delivery_history(
            db=db,
            retention_days=settings.INTEGRATION_DELIVERY_RETENTION_DAYS,
        )
        return result
