from __future__ import annotations

from datetime import datetime, timedelta, timezone
import hashlib
from typing import Dict, List, Optional, Tuple
from uuid import UUID

from sqlalchemy import and_, delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession
import logging

from app.models.integration import UserWebhook, WebhookDeliveryItem, WebhookDeliveryJob
from app.services.feed_service import feed_service
from config import settings

logger = logging.getLogger(__name__)


class DeliveryPlannerService:
    @staticmethod
    async def get_due_webhooks(*, db: AsyncSession, now: Optional[datetime] = None) -> List[UserWebhook]:
        now = now or datetime.now(timezone.utc)
        result = await db.execute(
            select(UserWebhook).where(
                UserWebhook.is_active.is_(True),
                UserWebhook.failure_count < UserWebhook.max_failures,
            )
        )
        webhooks = list(result.scalars().all())

        due: List[UserWebhook] = []
        min_interval = settings.integration_limits["min_batch_interval_minutes"]
        for webhook in webhooks:
            interval = max(webhook.batch_interval_minutes or min_interval, min_interval)
            anchor = webhook.last_attempted_at or webhook.created_at
            if not anchor or (now - anchor) >= timedelta(minutes=interval):
                due.append(webhook)
        return due

    @staticmethod
    async def compute_webhook_batch_items(
        *,
        webhook: UserWebhook,
        db: AsyncSession,
    ) -> Tuple[List[Dict], datetime, datetime]:
        now = datetime.now(timezone.utc)
        window_start = webhook.last_success_cursor_published_at or (now - timedelta(minutes=webhook.batch_interval_minutes))
        window_end = now
        limit = settings.integration_limits["max_items_per_batch"]

        if webhook.feed_id:
            feed = await feed_service.get_feed(feed_id=webhook.feed_id, user_id=webhook.user_id, db=db)
            if not feed:
                return [], window_start, window_end
            entries = await feed_service.get_feed_articles(
                feed=feed,
                user_id=webhook.user_id,
                db=db,
                limit=limit,
                since=window_start,
                sort="date",
            )
        else:
            bundle = await feed_service.get_bundle(bundle_id=webhook.bundle_id, user_id=webhook.user_id, db=db)
            if not bundle:
                return [], window_start, window_end
            entries = await feed_service.get_bundle_articles(
                bundle=bundle,
                user_id=webhook.user_id,
                db=db,
                limit=limit,
                since=window_start,
                sort="date",
            )

        payload_items: List[Dict] = []
        for entry in entries:
            article = entry["article"]
            payload_items.append(
                {
                    "article_id": str(article.article_id),
                    "title": article.title,
                    "url": article.url,
                    "source_name": article.source_name,
                    "published_date": article.published_date.isoformat() if article.published_date else None,
                    "topics": article.topics or [],
                    "relevance_score": entry.get("score"),
                }
            )
        return payload_items, window_start, window_end

    @staticmethod
    async def create_delivery_job(
        *,
        webhook: UserWebhook,
        items: List[Dict],
        window_start: datetime,
        window_end: datetime,
        db: AsyncSession,
    ) -> Optional[WebhookDeliveryJob]:
        if not items:
            return None

        digest_input = "|".join(item["article_id"] for item in items)
        payload_digest = hashlib.sha256(digest_input.encode("utf-8")).hexdigest()

        existing = await db.execute(
            select(WebhookDeliveryJob).where(
                WebhookDeliveryJob.webhook_id == webhook.webhook_id,
                WebhookDeliveryJob.window_end == window_end,
                WebhookDeliveryJob.payload_digest == payload_digest,
            )
        )
        if existing.scalar_one_or_none():
            return None

        job = WebhookDeliveryJob(
            webhook_id=webhook.webhook_id,
            window_start=window_start,
            window_end=window_end,
            status="pending",
            attempts=0,
            payload_digest=payload_digest,
            article_count=len(items),
        )
        db.add(job)
        await db.flush()

        for index, item in enumerate(items):
            db.add(
                WebhookDeliveryItem(
                    job_id=job.job_id,
                    article_id=UUID(item["article_id"]),
                    position=index,
                )
            )

        webhook.last_attempted_at = datetime.now(timezone.utc)
        await db.commit()
        await db.refresh(job)
        logger.info("Created webhook delivery job %s with %s items", job.job_id, len(items))
        return job

    @staticmethod
    async def mark_job_success(
        *,
        job: WebhookDeliveryJob,
        webhook: UserWebhook,
        latest_item: Optional[Dict],
        db: AsyncSession,
    ) -> None:
        now = datetime.now(timezone.utc)
        job.status = "delivered"
        job.updated_at = now
        webhook.last_triggered_at = now
        webhook.failure_count = 0
        if latest_item:
            published = latest_item.get("published_date")
            if published:
                webhook.last_success_cursor_published_at = datetime.fromisoformat(published)
            webhook.last_success_cursor_article_id = UUID(latest_item["article_id"])
        await db.commit()

    @staticmethod
    async def mark_job_failure(
        *,
        job: WebhookDeliveryJob,
        webhook: UserWebhook,
        error: str,
        db: AsyncSession,
    ) -> None:
        now = datetime.now(timezone.utc)
        job.attempts = int(job.attempts or 0) + 1
        webhook.failure_count = int(webhook.failure_count or 0) + 1
        job.last_error = error[:2000]
        job.updated_at = now

        if job.attempts >= settings.INTEGRATION_WEBHOOK_MAX_FAILURES or webhook.failure_count >= webhook.max_failures:
            job.status = "dead_letter"
            webhook.is_active = False
        else:
            backoff_minutes = [1, 5, 15, 60, 240][min(job.attempts - 1, 4)]
            job.next_retry_at = now + timedelta(minutes=backoff_minutes)
            job.status = "retry_pending"

        await db.commit()

    @staticmethod
    async def cleanup_delivery_history(
        *,
        db: AsyncSession,
        retention_days: Optional[int] = None,
    ) -> Dict[str, int]:
        retention = max(1, int(retention_days or settings.INTEGRATION_DELIVERY_RETENTION_DAYS))
        cutoff = datetime.now(timezone.utc) - timedelta(days=retention)
        terminal_statuses = ["delivered", "failed", "dead_letter", "cancelled"]

        count_result = await db.execute(
            select(func.count())
            .select_from(WebhookDeliveryJob)
            .where(
                WebhookDeliveryJob.status.in_(terminal_statuses),
                WebhookDeliveryJob.updated_at < cutoff,
            )
        )
        deletable_jobs = int(count_result.scalar() or 0)
        if deletable_jobs == 0:
            return {"deleted_jobs": 0, "retention_days": retention}

        # Items are removed via FK cascade (ondelete=CASCADE).
        await db.execute(
            delete(WebhookDeliveryJob).where(
                WebhookDeliveryJob.status.in_(terminal_statuses),
                WebhookDeliveryJob.updated_at < cutoff,
            )
        )
        await db.commit()
        logger.info(
            "Cleaned integration delivery history: deleted_jobs=%s retention_days=%s cutoff=%s",
            deletable_jobs,
            retention,
            cutoff.isoformat(),
        )
        return {"deleted_jobs": deletable_jobs, "retention_days": retention}


delivery_planner_service = DeliveryPlannerService()
