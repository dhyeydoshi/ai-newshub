from __future__ import annotations

from datetime import datetime, timedelta, timezone
import re
import secrets
from typing import Any, Dict, List, Optional
from uuid import UUID

from sqlalchemy import and_, desc, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import load_only
import logging

from app.models.article import Article
from app.models.feedback import ReadingHistory
from app.models.integration import (
    BundleFeedMembership,
    UserAPIKey,
    UserCustomFeed,
    UserFeedBundle,
    UserWebhook,
)
from app.services.rl_service import rl_service
from config import settings

logger = logging.getLogger(__name__)


class FeedService:
    @staticmethod
    def _slugify(name: str) -> str:
        base = re.sub(r"[^a-zA-Z0-9]+", "-", (name or "").strip().lower()).strip("-")
        base = base[:100] if base else "feed"
        suffix = secrets.token_hex(3)
        return f"{base}-{suffix}"

    @staticmethod
    def _normalize_filters(raw_filters: Optional[Dict[str, Any]]) -> Dict[str, Any]:
        defaults = {
            "topics": [],
            "exclude_topics": [],
            "categories": [],
            "keywords": [],
            "exclude_keywords": [],
            "sources": [],
            "exclude_sources": [],
            "language": "en",
            "exclude_read": True,
            "min_score": 0.0,
            "max_age_days": 7,
            "limit": 20,
            "sort_mode": "date",
        }
        if not raw_filters:
            return defaults

        normalized = dict(defaults)
        normalized.update(raw_filters)
        normalized["sort_mode"] = str(normalized.get("sort_mode", "date")).lower()
        return normalized

    @staticmethod
    async def _validate_api_key_owner(*, api_key_id: UUID, user_id: UUID, db: AsyncSession) -> UserAPIKey:
        result = await db.execute(
            select(UserAPIKey).where(
                UserAPIKey.api_key_id == api_key_id,
                UserAPIKey.user_id == user_id,
                UserAPIKey.is_active.is_(True),
            )
        )
        api_key = result.scalar_one_or_none()
        if not api_key:
            raise ValueError("API key not found or inactive")
        return api_key

    @classmethod
    async def create_feed(cls, *, user_id: UUID, data: Any, db: AsyncSession) -> UserCustomFeed:
        limits = settings.integration_limits
        await cls._validate_api_key_owner(api_key_id=data.api_key_id, user_id=user_id, db=db)

        feed_count_result = await db.execute(
            select(UserCustomFeed.feed_id).where(
                UserCustomFeed.user_id == user_id,
                UserCustomFeed.is_active.is_(True),
            )
        )
        active_count = len(feed_count_result.scalars().all())
        if active_count >= limits["max_feeds_per_user"]:
            raise ValueError(f"Maximum feeds reached ({limits['max_feeds_per_user']})")

        feed = UserCustomFeed(
            user_id=user_id,
            api_key_id=data.api_key_id,
            slug=cls._slugify(data.name),
            name=data.name,
            description=data.description,
            filters=cls._normalize_filters(data.filters.model_dump() if hasattr(data.filters, "model_dump") else data.filters),
            default_format=data.format,
            is_active=True,
        )
        db.add(feed)
        await db.commit()
        await db.refresh(feed)
        return feed

    @classmethod
    async def update_feed(cls, *, feed_id: UUID, user_id: UUID, data: Any, db: AsyncSession) -> UserCustomFeed:
        result = await db.execute(
            select(UserCustomFeed).where(
                UserCustomFeed.feed_id == feed_id,
                UserCustomFeed.user_id == user_id,
            )
        )
        feed = result.scalar_one_or_none()
        if not feed:
            raise ValueError("Feed not found")

        if data.name is not None:
            feed.name = data.name
        if data.description is not None:
            feed.description = data.description
        if data.filters is not None:
            payload = data.filters.model_dump() if hasattr(data.filters, "model_dump") else dict(data.filters)
            feed.filters = cls._normalize_filters(payload)
        if data.format is not None:
            feed.default_format = data.format
        if data.is_active is not None:
            feed.is_active = data.is_active

        feed.updated_at = datetime.now(timezone.utc)
        await db.commit()
        await db.refresh(feed)
        return feed

    @staticmethod
    async def delete_feed(*, feed_id: UUID, user_id: UUID, db: AsyncSession) -> bool:
        result = await db.execute(
            select(UserCustomFeed).where(
                UserCustomFeed.feed_id == feed_id,
                UserCustomFeed.user_id == user_id,
                UserCustomFeed.is_active.is_(True),
            )
        )
        feed = result.scalar_one_or_none()
        if not feed:
            return False

        feed.is_active = False
        feed.updated_at = datetime.now(timezone.utc)

        webhook_result = await db.execute(
            select(UserWebhook).where(
                UserWebhook.feed_id == feed.feed_id,
                UserWebhook.is_active.is_(True),
            )
        )
        for webhook in webhook_result.scalars():
            webhook.is_active = False

        await db.commit()
        return True

    @staticmethod
    async def list_feeds(*, user_id: UUID, db: AsyncSession) -> List[UserCustomFeed]:
        result = await db.execute(
            select(UserCustomFeed)
            .where(UserCustomFeed.user_id == user_id)
            .order_by(UserCustomFeed.created_at.desc())
        )
        return list(result.scalars().all())

    @staticmethod
    async def get_feed(*, feed_id: UUID, user_id: UUID, db: AsyncSession) -> Optional[UserCustomFeed]:
        result = await db.execute(
            select(UserCustomFeed).where(
                UserCustomFeed.feed_id == feed_id,
                UserCustomFeed.user_id == user_id,
            )
        )
        return result.scalar_one_or_none()

    @staticmethod
    async def get_feed_by_slug(*, slug: str, db: AsyncSession) -> Optional[UserCustomFeed]:
        result = await db.execute(
            select(UserCustomFeed).where(
                UserCustomFeed.slug == slug,
                UserCustomFeed.is_active.is_(True),
            )
        )
        return result.scalar_one_or_none()

    @classmethod
    async def create_bundle(cls, *, user_id: UUID, data: Any, db: AsyncSession) -> UserFeedBundle:
        limits = settings.integration_limits
        await cls._validate_api_key_owner(api_key_id=data.api_key_id, user_id=user_id, db=db)

        unique_feed_ids = list(dict.fromkeys(data.feed_ids))
        if len(unique_feed_ids) != len(data.feed_ids):
            raise ValueError("Duplicate feed IDs are not allowed in a bundle")

        bundle_count_result = await db.execute(
            select(UserFeedBundle.bundle_id).where(
                UserFeedBundle.user_id == user_id,
                UserFeedBundle.is_active.is_(True),
            )
        )
        active_count = len(bundle_count_result.scalars().all())
        if active_count >= limits["max_bundles_per_user"]:
            raise ValueError(f"Maximum bundles reached ({limits['max_bundles_per_user']})")

        if len(unique_feed_ids) > limits["max_feeds_per_bundle"]:
            raise ValueError(f"Bundle can contain at most {limits['max_feeds_per_bundle']} feeds")

        feeds_result = await db.execute(
            select(UserCustomFeed).where(
                UserCustomFeed.feed_id.in_(unique_feed_ids),
                UserCustomFeed.user_id == user_id,
                UserCustomFeed.is_active.is_(True),
            )
        )
        feeds = list(feeds_result.scalars().all())
        if len(feeds) != len(unique_feed_ids):
            raise ValueError("One or more feed IDs are invalid")

        bundle = UserFeedBundle(
            user_id=user_id,
            api_key_id=data.api_key_id,
            slug=cls._slugify(data.name),
            name=data.name,
            description=data.description,
            default_format=data.format,
            is_active=True,
        )
        db.add(bundle)
        await db.flush()

        for feed_id in unique_feed_ids:
            db.add(BundleFeedMembership(bundle_id=bundle.bundle_id, feed_id=feed_id))

        await db.commit()
        await db.refresh(bundle)
        return bundle

    @staticmethod
    async def update_bundle(*, bundle_id: UUID, user_id: UUID, data: Any, db: AsyncSession) -> UserFeedBundle:
        result = await db.execute(
            select(UserFeedBundle).where(
                UserFeedBundle.bundle_id == bundle_id,
                UserFeedBundle.user_id == user_id,
            )
        )
        bundle = result.scalar_one_or_none()
        if not bundle:
            raise ValueError("Bundle not found")

        if data.name is not None:
            bundle.name = data.name
        if data.description is not None:
            bundle.description = data.description
        if data.format is not None:
            bundle.default_format = data.format
        if data.is_active is not None:
            bundle.is_active = data.is_active

        bundle.updated_at = datetime.now(timezone.utc)
        await db.commit()
        await db.refresh(bundle)
        return bundle

    @staticmethod
    async def delete_bundle(*, bundle_id: UUID, user_id: UUID, db: AsyncSession) -> bool:
        result = await db.execute(
            select(UserFeedBundle).where(
                UserFeedBundle.bundle_id == bundle_id,
                UserFeedBundle.user_id == user_id,
                UserFeedBundle.is_active.is_(True),
            )
        )
        bundle = result.scalar_one_or_none()
        if not bundle:
            return False

        bundle.is_active = False
        bundle.updated_at = datetime.now(timezone.utc)

        webhook_result = await db.execute(
            select(UserWebhook).where(
                UserWebhook.bundle_id == bundle.bundle_id,
                UserWebhook.is_active.is_(True),
            )
        )
        for webhook in webhook_result.scalars():
            webhook.is_active = False

        await db.commit()
        return True

    @staticmethod
    async def list_bundles(*, user_id: UUID, db: AsyncSession) -> List[UserFeedBundle]:
        result = await db.execute(
            select(UserFeedBundle)
            .where(UserFeedBundle.user_id == user_id)
            .order_by(UserFeedBundle.created_at.desc())
        )
        return list(result.scalars().all())

    @staticmethod
    async def get_bundle(*, bundle_id: UUID, user_id: UUID, db: AsyncSession) -> Optional[UserFeedBundle]:
        result = await db.execute(
            select(UserFeedBundle).where(
                UserFeedBundle.bundle_id == bundle_id,
                UserFeedBundle.user_id == user_id,
            )
        )
        return result.scalar_one_or_none()

    @staticmethod
    async def get_bundle_by_slug(*, slug: str, db: AsyncSession) -> Optional[UserFeedBundle]:
        result = await db.execute(
            select(UserFeedBundle).where(
                UserFeedBundle.slug == slug,
                UserFeedBundle.is_active.is_(True),
            )
        )
        return result.scalar_one_or_none()

    @staticmethod
    async def add_feed_to_bundle(*, bundle_id: UUID, feed_id: UUID, user_id: UUID, db: AsyncSession) -> None:
        bundle_result = await db.execute(
            select(UserFeedBundle).where(
                UserFeedBundle.bundle_id == bundle_id,
                UserFeedBundle.user_id == user_id,
                UserFeedBundle.is_active.is_(True),
            )
        )
        bundle = bundle_result.scalar_one_or_none()
        if not bundle:
            raise ValueError("Bundle not found")

        feed_result = await db.execute(
            select(UserCustomFeed).where(
                UserCustomFeed.feed_id == feed_id,
                UserCustomFeed.user_id == user_id,
                UserCustomFeed.is_active.is_(True),
            )
        )
        feed = feed_result.scalar_one_or_none()
        if not feed:
            raise ValueError("Feed not found")

        membership_exists = await db.execute(
            select(BundleFeedMembership).where(
                BundleFeedMembership.bundle_id == bundle_id,
                BundleFeedMembership.feed_id == feed_id,
            )
        )
        if membership_exists.scalar_one_or_none():
            return

        count_result = await db.execute(
            select(BundleFeedMembership.id).where(BundleFeedMembership.bundle_id == bundle_id)
        )
        if len(count_result.scalars().all()) >= settings.integration_limits["max_feeds_per_bundle"]:
            raise ValueError(f"Bundle can contain at most {settings.integration_limits['max_feeds_per_bundle']} feeds")

        db.add(BundleFeedMembership(bundle_id=bundle_id, feed_id=feed_id))
        await db.commit()

    @staticmethod
    async def remove_feed_from_bundle(*, bundle_id: UUID, feed_id: UUID, user_id: UUID, db: AsyncSession) -> bool:
        bundle_result = await db.execute(
            select(UserFeedBundle).where(
                UserFeedBundle.bundle_id == bundle_id,
                UserFeedBundle.user_id == user_id,
            )
        )
        if not bundle_result.scalar_one_or_none():
            return False

        membership_result = await db.execute(
            select(BundleFeedMembership).where(
                BundleFeedMembership.bundle_id == bundle_id,
                BundleFeedMembership.feed_id == feed_id,
            )
        )
        membership = membership_result.scalar_one_or_none()
        if not membership:
            return False

        await db.delete(membership)
        await db.commit()
        return True

    @staticmethod
    async def get_bundle_feed_ids(*, bundle_id: UUID, db: AsyncSession) -> List[UUID]:
        result = await db.execute(
            select(BundleFeedMembership.feed_id).where(BundleFeedMembership.bundle_id == bundle_id)
        )
        return [row[0] for row in result.fetchall()]

    @classmethod
    async def get_feed_articles(
        cls,
        *,
        feed: UserCustomFeed,
        user_id: Optional[UUID],
        db: AsyncSession,
        limit: Optional[int] = None,
        since: Optional[datetime] = None,
        sort: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        filters = cls._normalize_filters(feed.filters or {})
        requested_limit = limit or filters.get("limit", 20)
        hard_limit = min(max(1, requested_limit), 100)
        sort_mode = (sort or filters.get("sort_mode", "date")).lower()
        min_score = float(filters.get("min_score", 0.0) or 0.0)
        needs_scoring = bool(user_id and (sort_mode == "relevance" or min_score > 0.0))

        keywords = filters.get("keywords") or []
        exclude_keywords = filters.get("exclude_keywords") or []
        needs_content_column = bool(needs_scoring or keywords or exclude_keywords)

        load_columns = [
            Article.article_id,
            Article.title,
            Article.excerpt,
            Article.url,
            Article.source_name,
            Article.author,
            Article.image_url,
            Article.topics,
            Article.category,
            Article.published_date,
            Article.language,
            Article.is_active,
            Article.moderation_status,
            Article.deleted_at,
        ]
        if needs_content_column:
            load_columns.append(Article.content)

        query = (
            select(Article)
            .options(load_only(*load_columns))
            .where(
                Article.is_active.is_(True),
                Article.moderation_status == "approved",
                Article.deleted_at.is_(None),
            )
        )

        topics = filters.get("topics") or []
        if topics:
            query = query.where(Article.topics.op("&&")(topics))

        exclude_topics = filters.get("exclude_topics") or []
        if exclude_topics:
            query = query.where(~Article.topics.op("&&")(exclude_topics))

        categories = filters.get("categories") or []
        if categories:
            query = query.where(Article.category.in_(categories))

        language = filters.get("language")
        if language:
            query = query.where(Article.language == language)

        sources = filters.get("sources") or []
        if sources:
            query = query.where(Article.source_name.in_(sources))

        exclude_sources = filters.get("exclude_sources") or []
        if exclude_sources:
            query = query.where(~Article.source_name.in_(exclude_sources))

        if keywords:
            keyword_clauses = []
            for keyword in keywords:
                pattern = f"%{keyword}%"
                keyword_clauses.append(
                    or_(
                        Article.title.ilike(pattern),
                        Article.excerpt.ilike(pattern),
                        Article.content.ilike(pattern),
                    )
                )
            query = query.where(or_(*keyword_clauses))

        if exclude_keywords:
            for keyword in exclude_keywords:
                pattern = f"%{keyword}%"
                query = query.where(
                    and_(
                        ~Article.title.ilike(pattern),
                        ~Article.excerpt.ilike(pattern),
                        ~Article.content.ilike(pattern),
                    )
                )

        max_age_days = int(filters.get("max_age_days", 7) or 7)
        threshold = datetime.now(timezone.utc) - timedelta(days=max_age_days)
        query = query.where(Article.published_date >= threshold)

        if since is not None:
            query = query.where(Article.published_date > since)

        if filters.get("exclude_read", True) and user_id:
            read_subquery = select(ReadingHistory.article_id).where(ReadingHistory.user_id == user_id)
            query = query.where(Article.article_id.not_in(read_subquery))

        candidate_limit = hard_limit if not needs_scoring else min(200, hard_limit * 3)
        query = query.order_by(desc(Article.published_date)).limit(candidate_limit)
        result = await db.execute(query)
        articles = list(result.scalars().all())

        if not articles:
            return []

        article_entries: List[Dict[str, Any]] = [{"article": article, "score": None} for article in articles]

        if needs_scoring:
            recs = await rl_service.get_recommendations(
                user_id=str(user_id),
                candidate_articles=[article.to_dict() for article in articles],
                top_k=len(articles),
            )
            score_map = {rec["article_id"]: float(rec.get("score", 0.0)) for rec in recs}
            article_entries = []
            for article in articles:
                score = score_map.get(str(article.article_id), 0.0)
                if score < min_score:
                    continue
                article_entries.append({"article": article, "score": score})

            if sort_mode == "relevance":
                article_entries.sort(
                    key=lambda item: (item["score"] or 0.0, item["article"].published_date),
                    reverse=True,
                )
            else:
                article_entries.sort(key=lambda item: item["article"].published_date, reverse=True)
        else:
            article_entries.sort(key=lambda item: item["article"].published_date, reverse=True)

        return article_entries[:hard_limit]

    @classmethod
    async def get_bundle_articles(
        cls,
        *,
        bundle: UserFeedBundle,
        user_id: Optional[UUID],
        db: AsyncSession,
        limit: Optional[int] = None,
        since: Optional[datetime] = None,
        sort: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        feed_ids = await cls.get_bundle_feed_ids(bundle_id=bundle.bundle_id, db=db)
        if not feed_ids:
            return []

        feed_result = await db.execute(
            select(UserCustomFeed).where(
                UserCustomFeed.feed_id.in_(feed_ids),
                UserCustomFeed.is_active.is_(True),
            )
        )
        feeds = list(feed_result.scalars().all())

        merged: Dict[UUID, Dict[str, Any]] = {}
        for feed in feeds:
            items = await cls.get_feed_articles(
                feed=feed,
                user_id=user_id,
                db=db,
                limit=limit,
                since=since,
                sort=sort,
            )
            for item in items:
                article = item["article"]
                existing = merged.get(article.article_id)
                if not existing:
                    merged[article.article_id] = item
                    continue
                if (item.get("score") or 0.0) > (existing.get("score") or 0.0):
                    merged[article.article_id] = item

        merged_items = list(merged.values())
        sort_mode = (sort or "date").lower()
        if sort_mode == "relevance":
            merged_items.sort(
                key=lambda item: (item.get("score") or 0.0, item["article"].published_date),
                reverse=True,
            )
        else:
            merged_items.sort(key=lambda item: item["article"].published_date, reverse=True)

        hard_limit = min(max(1, limit or 20), 100)
        return merged_items[:hard_limit]


feed_service = FeedService()
