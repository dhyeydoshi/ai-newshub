from typing import List, Dict, Any, Optional, Set
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from datetime import datetime, timezone
import logging

from app.models.article import Article

logger = logging.getLogger(__name__)


class ArticlePersistenceService:

    async def save_articles(
        self,
        articles: List[Dict[str, Any]],
        db: AsyncSession,
        auto_approve: bool = True
    ) -> Dict[str, Any]:
        if not articles:
            return {'total': 0, 'saved': 0, 'duplicates': 0, 'errors': 0}

        # Collect URLs and content hashes for batch deduplication
        urls = [a['url'] for a in articles if a.get('url')]
        content_hashes = [a['content_hash'] for a in articles if a.get('content_hash')]

        # Batch query existing URLs
        existing_urls: Set[str] = set()
        if urls:
            result = await db.execute(
                select(Article.url).where(Article.url.in_(urls))
            )
            existing_urls = {row[0] for row in result.fetchall()}

        # Batch query existing content hashes
        existing_hashes: Set[str] = set()
        if content_hashes:
            result = await db.execute(
                select(Article.content_hash).where(Article.content_hash.in_(content_hashes))
            )
            existing_hashes = {row[0] for row in result.fetchall()}

        logger.info(f"Database check: {len(existing_urls)} existing URLs, {len(existing_hashes)} existing hashes")

        # Build list of articles to insert
        articles_to_insert: List[Article] = []
        saved_count = 0
        duplicate_count = 0
        error_count = 0

        for data in articles:
            try:
                url = data.get('url', '')
                content_hash = data.get('content_hash', '')

                # Skip if URL or content hash already exists
                if url in existing_urls:
                    duplicate_count += 1
                    continue
                if content_hash and content_hash in existing_hashes:
                    duplicate_count += 1
                    continue

                # Create Article from pre-validated data
                article = Article(
                    title=data.get('title', ''),
                    content=data.get('content', ''),
                    excerpt=data.get('description'),
                    url=url,
                    source_name=data.get('source', 'Unknown'),
                    source_url=data.get('source_url'),
                    author=data.get('author'),
                    category=data.get('category'),
                    topics=data.get('topics', [])[:20],
                    tags=data.get('tags', [])[:50],
                    language=data.get('language', 'en'),
                    meta_data=data.get('metadata', {}),
                    published_date=data.get('published_date', datetime.now(timezone.utc)),
                    scraped_date=datetime.now(timezone.utc),
                    word_count=data.get('word_count', 0),
                    reading_time_minutes=data.get('reading_time_minutes', 1),
                    content_hash=content_hash,
                    image_url=data.get('image_url'),
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
                logger.error(f"Error creating Article: {e}")

        # Bulk insert
        if articles_to_insert:
            try:
                db.add_all(articles_to_insert)
                await db.commit()
                logger.info(f"Bulk inserted {saved_count} articles")
            except Exception as e:
                await db.rollback()
                logger.error(f"Bulk insert failed: {e}")
                raise

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
        query = select(Article).where(
            Article.is_active == True,
            Article.moderation_status == 'approved',
            Article.deleted_at.is_(None)
        )

        if category:
            query = query.where(Article.category == category)

        if topics:
            query = query.where(Article.topics.op('&&')(topics))

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
            query = query.where(Article.topics.op('&&')(topics))

        result = await db.execute(query)
        count = result.scalar() or 0

        return count


# Singleton instance
article_persistence_service = ArticlePersistenceService()
