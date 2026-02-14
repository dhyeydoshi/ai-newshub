from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Sequence, Tuple, Union
import logging

from config import settings
from app.core.sanitizer import ContentSanitizer
from app.services.article_persistence import article_persistence_service
from app.services.news_aggregator import NewsAggregatorService
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)


class NewsIngestionService:
    """Orchestrates source selection, normalization, and persistence for news ingestion."""

    VALID_SOURCES = {"newsapi", "gdelt", "rss"}

    @staticmethod
    def normalize_topics(topics: Optional[Sequence[str]]) -> List[str]:
        if not topics:
            return []

        normalized: List[str] = []
        seen = set()
        for topic in topics:
            cleaned = ContentSanitizer.sanitize_text(str(topic or ""), max_length=100).lower()
            if not cleaned or cleaned in seen:
                continue
            seen.add(cleaned)
            normalized.append(cleaned)
        return normalized

    @classmethod
    def resolve_sources(cls, sources: Optional[Union[str, Sequence[str]]]) -> List[str]:
        if sources is None:
            source_list = [s.strip().lower() for s in settings.NEWS_SOURCES if str(s).strip()]
        elif isinstance(sources, str):
            source_list = [s.strip().lower() for s in sources.split(",") if s.strip()]
        else:
            source_list = [str(s).strip().lower() for s in sources if str(s).strip()]

        if settings.ENABLE_RSS_FEEDS and "rss" not in source_list:
            source_list.append("rss")

        invalid_sources = sorted(set(source_list) - cls.VALID_SOURCES)
        if invalid_sources:
            raise ValueError(f"Invalid sources: {invalid_sources}. Valid: {sorted(cls.VALID_SOURCES)}")

        # Preserve order while removing duplicates
        deduped_sources = list(dict.fromkeys(source_list))
        return deduped_sources

    @staticmethod
    def resolve_feed_urls(source_list: Sequence[str], topics: Optional[Sequence[str]]) -> Optional[List[str]]:
        if "rss" not in source_list or not settings.ENABLE_RSS_FEEDS:
            return None
        return settings.get_rss_feed_urls_for_topics(list(topics or []))

    @classmethod
    def prepare_articles_for_persistence(
        cls,
        articles: Sequence[Dict[str, Any]],
        topic_hints: Optional[Sequence[str]] = None
    ) -> Tuple[List[Dict[str, Any]], Dict[str, int]]:
        """Normalize and validate aggregated articles before DB persistence."""
        normalized_topic_hints = cls.normalize_topics(topic_hints)
        prepared_articles: List[Dict[str, Any]] = []
        seen_urls = set()
        seen_hashes = set()

        stats = {
            "input_count": len(articles),
            "accepted_count": 0,
            "dropped_invalid": 0,
            "dropped_duplicates": 0,
        }

        for raw_article in articles:
            if not isinstance(raw_article, dict):
                stats["dropped_invalid"] += 1
                continue

            title = ContentSanitizer.sanitize_text(raw_article.get("title"), max_length=2000)
            url = ContentSanitizer.sanitize_url(raw_article.get("url"), max_length=2048)
            source = ContentSanitizer.sanitize_text(raw_article.get("source"), max_length=255)

            raw_content = raw_article.get("content") or raw_article.get("description") or ""
            content = ContentSanitizer.sanitize_text(raw_content, max_length=50000)
            description = raw_article.get("description")
            if description is not None:
                description = ContentSanitizer.sanitize_text(description, max_length=1000) or None

            if not title or not url or not source or not content:
                stats["dropped_invalid"] += 1
                continue

            content_hash = str(raw_article.get("content_hash") or "").strip() or None
            if url in seen_urls or (content_hash and content_hash in seen_hashes):
                stats["dropped_duplicates"] += 1
                continue

            seen_urls.add(url)
            if content_hash:
                seen_hashes.add(content_hash)

            topics = cls.normalize_topics((raw_article.get("topics") or []) + normalized_topic_hints)
            tags = cls.normalize_topics(raw_article.get("tags") or [])

            prepared = dict(raw_article)
            prepared["title"] = title
            prepared["url"] = url
            prepared["source"] = source
            prepared["content"] = content
            prepared["description"] = description
            prepared["topics"] = topics[:20]
            prepared["tags"] = tags[:50]
            prepared["language"] = (
                ContentSanitizer.sanitize_text(raw_article.get("language"), max_length=10).lower() or "en"
            )

            if not prepared.get("published_date"):
                prepared["published_date"] = datetime.now(timezone.utc)

            prepared_articles.append(prepared)
            stats["accepted_count"] += 1

        return prepared_articles, stats

    async def aggregate_and_persist(
        self,
        *,
        aggregator: NewsAggregatorService,
        db: Optional[AsyncSession],
        query: Optional[str],
        sources: Optional[Union[str, Sequence[str]]],
        limit: int,
        deduplicate: bool,
        use_cache: bool,
        topics: Optional[Sequence[str]],
        category: Optional[str],
        language: str,
        save_to_db: bool,
        auto_approve: bool = True,
    ) -> Dict[str, Any]:
        source_list = self.resolve_sources(sources)
        normalized_topics = self.normalize_topics(topics)
        feed_urls = self.resolve_feed_urls(source_list, normalized_topics)

        fetched_articles = await aggregator.aggregate_news(
            query=query,
            sources=source_list,
            limit=limit,
            deduplicate=deduplicate,
            use_cache=use_cache,
            topics=normalized_topics,
            category=category,
            language=language,
            feed_urls=feed_urls,
        )

        prepared_articles, pipeline_stats = self.prepare_articles_for_persistence(
            fetched_articles,
            topic_hints=normalized_topics
        )

        save_stats = {"total": 0, "saved": 0, "duplicates": 0, "errors": 0}
        if save_to_db and prepared_articles and db is not None:
            save_stats = await article_persistence_service.save_articles(
                articles=prepared_articles,
                db=db,
                auto_approve=auto_approve
            )

        logger.info(
            "Ingestion pipeline completed: fetched=%s accepted=%s dropped_invalid=%s dropped_duplicates=%s saved=%s",
            len(fetched_articles),
            pipeline_stats["accepted_count"],
            pipeline_stats["dropped_invalid"],
            pipeline_stats["dropped_duplicates"],
            save_stats.get("saved", 0),
        )

        return {
            "articles": prepared_articles,
            "sources_used": source_list,
            "pipeline_stats": pipeline_stats,
            "save_stats": save_stats,
        }

    async def fetch_rss_and_prepare(
        self,
        *,
        aggregator: NewsAggregatorService,
        feed_urls: Sequence[str],
        limit_per_feed: int,
        deduplicate: bool,
        topic_hints: Optional[Sequence[str]] = None,
        language: str = "en",
    ) -> Dict[str, Any]:
        fetched_articles = await aggregator.fetch_from_rss_feeds(
            feed_urls=list(feed_urls),
            limit_per_feed=limit_per_feed,
            deduplicate=deduplicate,
            language=language,
        )

        prepared_articles, pipeline_stats = self.prepare_articles_for_persistence(
            fetched_articles,
            topic_hints=topic_hints
        )

        return {
            "articles": prepared_articles,
            "pipeline_stats": pipeline_stats,
        }


news_ingestion_service = NewsIngestionService()
