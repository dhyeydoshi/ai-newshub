"""
Article Persistence Service
Handles saving fetched articles to database with deduplication
"""
from typing import List, Dict, Any, Optional, Set
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from datetime import datetime, timezone
import logging

from app.models.article import Article
from app.services.news_aggregator import ArticleDeduplicator
from app.utils.date_parser import parse_flexible_date, ensure_timezone_aware

logger = logging.getLogger(__name__)


class ArticlePersistenceService:
    """Service for persisting articles to database"""

    def __init__(self):
        self.deduplicator = ArticleDeduplicator()

    async def save_articles(
        self,
        articles: List[Dict[str, Any]],
        db: AsyncSession,
        auto_approve: bool = True
    ) -> Dict[str, Any]:
        """
        Save articles to database with deduplication using batch operations

        OPTIMIZED: Uses batch queries and bulk insert for better performance

        Args:
            articles: List of article dictionaries from aggregator
            db: Database session
            auto_approve: Automatically approve articles (set moderation_status to 'approved')

        Returns:
            Dictionary with statistics about saved articles
        """
        if not articles:
            return {
                'total': 0,
                'saved': 0,
                'duplicates': 0,
                'errors': 0
            }

        saved_count = 0
        duplicate_count = 0
        error_count = 0

        # OPTIMIZATION 1: Batch fetch existing URLs and content hashes
        urls = [a.get('url') for a in articles if a.get('url')]
        content_hashes = []

        for article_data in articles:
            content = article_data.get('content', '') or article_data.get('description', '')
            if content:
                content_hash = self.deduplicator.generate_content_hash(content)
                content_hashes.append(content_hash)

        # Query existing articles by URL in one batch
        existing_urls: Set[str] = set()
        if urls:
            result = await db.execute(
                select(Article.url).where(Article.url.in_(urls))
            )
            existing_urls = {row[0] for row in result.fetchall()}

        # Query existing articles by content hash in one batch
        existing_hashes: Set[str] = set()
        if content_hashes:
            result = await db.execute(
                select(Article.content_hash).where(Article.content_hash.in_(content_hashes))
            )
            existing_hashes = {row[0] for row in result.fetchall()}

        logger.info(f"Found {len(existing_urls)} existing URLs and {len(existing_hashes)} existing content hashes")

        # OPTIMIZATION 2: Prepare articles for bulk insert
        articles_to_insert = []

        for article_data in articles:
            try:
                url = article_data.get('url', '')

                # Check if URL already exists
                if url in existing_urls:
                    duplicate_count += 1
                    logger.debug(f"Skipping duplicate URL: {article_data.get('title', 'Unknown')}")
                    continue

                # Generate content hash for deduplication
                content = article_data.get('content', '') or article_data.get('description', '')
                content_hash = self.deduplicator.generate_content_hash(content)

                # Check if content hash exists
                if content_hash in existing_hashes:
                    duplicate_count += 1
                    logger.debug(f"Skipping duplicate content: {article_data.get('title', 'Unknown')}")
                    continue

                # Calculate word count and reading time
                word_count = len(content.split()) if content else 0
                reading_time = max(1, word_count // 200)  # Average reading speed: 200 words/min

                # Parse published date
                published_date = article_data.get('published_date')
                published_date = parse_flexible_date(published_date)

                # Ensure published_date is timezone-aware
                published_date = ensure_timezone_aware(published_date)

                # Extract topics and tags
                topics = article_data.get('topics', [])
                if isinstance(topics, str):
                    topics = [t.strip() for t in topics.split(',') if t.strip()]
                elif not isinstance(topics, list):
                    topics = []

                tags = article_data.get('tags', [])
                if isinstance(tags, str):
                    tags = [t.strip() for t in tags.split(',') if t.strip()]
                elif not isinstance(tags, list):
                    tags = []

                # Extract metadata
                metadata = article_data.get('metadata', {})
                if not isinstance(metadata, dict):
                    metadata = {}

                # Create Article instance
                article = Article(
                    title=article_data.get('title', '')[:2000],
                    content=content[:50000],
                    excerpt=article_data.get('description', '')[:1000],
                    url=url[:2048],
                    source_name=article_data.get('source', 'Unknown')[:255],
                    source_url=article_data.get('source_url', '')[:2048] if article_data.get('source_url') else None,
                    author=article_data.get('author', '')[:255] if article_data.get('author') else None,
                    category=article_data.get('category', '')[:100] if article_data.get('category') else None,
                    topics=topics[:20],  # Limit to 20 topics
                    tags=tags[:50],  # Limit to 50 tags
                    language=article_data.get('language', 'en')[:10],
                    meta_data=metadata,
                    published_date=published_date,
                    scraped_date=datetime.now(timezone.utc),
                    word_count=word_count,
                    reading_time_minutes=reading_time,
                    content_hash=content_hash,
                    image_url=article_data.get('image_url', '')[:1000] if article_data.get('image_url') else None,
                    is_active=True,
                    moderation_status='approved' if auto_approve else 'pending',
                    total_views=0,
                    total_clicks=0,
                    avg_time_spent=0.0,
                    click_through_rate=0.0
                )

                articles_to_insert.append(article)
                saved_count += 1

            except Exception as e:
                error_count += 1
                logger.error(f"Error preparing article: {e}", exc_info=True)
                continue

        # OPTIMIZATION 3: Bulk insert all articles
        if articles_to_insert:
            try:
                db.add_all(articles_to_insert)
                await db.commit()
                logger.info(f"Successfully bulk inserted {saved_count} articles to database")
            except Exception as e:
                await db.rollback()
                logger.error(f"Error bulk inserting articles to database: {e}")
                raise
        else:
            logger.info("No new articles to insert")

        return {
            'total': len(articles),
            'saved': saved_count,
            'duplicates': duplicate_count,
            'errors': error_count
        }

    async def get_recent_articles(
        self,
        db: AsyncSession,
        limit: int = 50,
        offset: int = 0,
        category: Optional[str] = None,
        topics: Optional[List[str]] = None,
        language: str = 'en'
    ) -> List[Article]:
        """
        Get recent articles from database

        Args:
            db: Database session
            limit: Maximum number of articles
            offset: Offset for pagination
            category: Filter by category
            topics: Filter by topics
            language: Filter by language

        Returns:
            List of Article objects
        """
        query = select(Article).where(
            Article.is_active == True,
            Article.moderation_status == 'approved',
            Article.deleted_at.is_(None)
        )

        if category:
            query = query.where(Article.category == category)

        if topics:
            query = query.where(Article.topics.overlap(topics))

        if language:
            query = query.where(Article.language == language)

        query = query.order_by(Article.published_date.desc()).limit(limit).offset(offset)

        result = await db.execute(query)
        articles = result.scalars().all()

        return articles

    async def get_article_count(
        self,
        db: AsyncSession,
        category: Optional[str] = None,
        topics: Optional[List[str]] = None
    ) -> int:
        """Get total count of articles matching filters"""
        query = select(func.count(Article.article_id)).where(
            Article.is_active == True,
            Article.moderation_status == 'approved',
            Article.deleted_at.is_(None)
        )

        if category:
            query = query.where(Article.category == category)

        if topics:
            query = query.where(Article.topics.overlap(topics))

        result = await db.execute(query)
        count = result.scalar() or 0

        return count


# Singleton instance
article_persistence_service = ArticlePersistenceService()
