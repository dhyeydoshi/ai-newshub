from datetime import datetime, timezone, timedelta
import logging
from typing import Optional, List
import asyncio

from app.celery_config import celery_app
from config import settings

logger = logging.getLogger(__name__)


@celery_app.task(
    name='app.tasks.news_tasks.fetch_and_save_news',
    bind=True,
    autoretry_for=(Exception,),
    retry_kwargs={'max_retries': 3, 'countdown': 300},  # Retry 3 times, wait 5 min
    retry_backoff=True,
    retry_jitter=True
)
def fetch_and_save_news(
    self,
    queries: Optional[List[str]] = None,
    sources: Optional[List[str]] = None,
    limit_per_query: int = 50
):
    return asyncio.run(_async_fetch_and_save_news(queries, sources, limit_per_query))


async def _async_fetch_and_save_news(
    queries: Optional[List[str]] = None,
    sources: Optional[List[str]] = None,
    limit_per_query: int = 50
):
    try:
        logger.info("Celery Task: Starting scheduled news fetch...")

        # Import here to avoid circular imports
        from app.services.news_aggregator import NewsAggregatorService
        from app.services.article_persistence import article_persistence_service
        from app.core.database import AsyncSessionLocal
        from app.dependencies.cache import invalidate_article_cache
        from app.core.cache import init_cache_manager
        import redis.asyncio as aioredis

        # Default queries if none provided
        if not queries:
            queries = settings.NEWS_FETCH_QUERIES

        if not sources:
            sources = settings.NEWS_SOURCES

        # Connect to Redis
        redis_client = aioredis.from_url(
            settings.REDIS_URL,
            encoding="utf-8",
            decode_responses=True
        )

        try:
            init_cache_manager(
                redis_client,
                default_ttl=settings.REDIS_CACHE_TTL,
                compression_threshold=1024,
                key_prefix="news_app"
            )
            logger.info("Cache manager initialized for task")

            # Create aggregator
            aggregator = NewsAggregatorService(
                redis_client=redis_client,
                newsapi_key=settings.NEWS_API_KEY,
                cache_ttl=settings.NEWS_CACHE_TTL
            )

            # Get database session
            async with AsyncSessionLocal() as db:
                total_saved = 0
                total_duplicates = 0
                total_errors = 0

                for query in queries:
                    logger.info(f"Fetching news for query: {query}")

                    try:
                        topic_hint = [query] if query else None
                        articles = await aggregator.aggregate_news(
                            query=query,
                            sources=sources,
                            limit=limit_per_query,
                            deduplicate=True,
                            use_cache=False,
                            topics=topic_hint
                        )

                        if articles:
                            # Save to database
                            stats = await article_persistence_service.save_articles(
                                articles=articles,
                                db=db,
                                auto_approve=True
                            )

                            total_saved += stats['saved']
                            total_duplicates += stats['duplicates']
                            total_errors += stats['errors']

                            logger.info(
                                f"Query '{query}': Saved {stats['saved']}, "
                                f"Duplicates {stats['duplicates']}, "
                                f"Errors {stats['errors']}"
                            )
                    except Exception as e:
                        logger.error(f"Error fetching for query '{query}': {e}", exc_info=True)
                        total_errors += 1
                        continue

                # CRITICAL: Invalidate endpoint cache after fetching new articles
                if total_saved > 0:
                    logger.info(f"Invalidating article cache after saving {total_saved} new articles")
                    await invalidate_article_cache()
                    logger.info(" Article cache invalidated - users will see fresh data")

                logger.info(
                    f"Scheduled fetch complete: "
                    f"Total saved: {total_saved}, "
                    f"Total duplicates: {total_duplicates}, "
                    f"Total errors: {total_errors}"
                )

                # Update last fetch timestamp in Redis
                await redis_client.set(
                    'news:last_fetch_timestamp',
                    datetime.now(timezone.utc).isoformat(),
                    ex=86400  # Expire after 24 hours
                )

                return {
                    'status': 'success',
                    'saved': total_saved,
                    'duplicates': total_duplicates,
                    'errors': total_errors,
                    'timestamp': datetime.now(timezone.utc).isoformat(),
                    'cache_invalidated': total_saved > 0
                }

        finally:
            await redis_client.close()

    except Exception as e:
        logger.error(f"Error in scheduled news fetch: {e}", exc_info=True)
        raise


@celery_app.task(
    name='app.tasks.news_tasks.fetch_rss_feeds',
    bind=True,
    autoretry_for=(Exception,),
    retry_kwargs={'max_retries': 3, 'countdown': 300},
    retry_backoff=True,
    retry_jitter=True
)
def fetch_rss_feeds(self, feed_urls: Optional[List[str]] = None):
    return asyncio.run(_async_fetch_rss_feeds(feed_urls))


async def _async_fetch_rss_feeds(feed_urls: Optional[List[str]] = None):
    try:
        # Import here to avoid circular imports
        from app.services.news_aggregator import NewsAggregatorService
        from app.services.article_persistence import article_persistence_service
        from app.core.database import AsyncSessionLocal
        from app.dependencies.cache import invalidate_article_cache
        from app.core.cache import init_cache_manager
        import redis.asyncio as aioredis

        if not feed_urls:
            feed_urls = settings.get_all_rss_feed_urls()

        logger.info(f"Celery Task: Fetching from {len(feed_urls)} RSS feeds...")

        # Connect to Redis
        redis_client = aioredis.from_url(
            settings.REDIS_URL,
            encoding="utf-8",
            decode_responses=True
        )

        try:
            # Initialize cache manager
            cache_manager = init_cache_manager(
                redis_client,
                default_ttl=settings.REDIS_CACHE_TTL,
                compression_threshold=1024,
                key_prefix="news_app"
            )

            # Create aggregator
            aggregator = NewsAggregatorService(
                redis_client=redis_client,
                newsapi_key=settings.NEWS_API_KEY,
                cache_ttl=settings.NEWS_CACHE_TTL
            )

            # Fetch articles from RSS feeds
            articles = await aggregator.fetch_from_rss_feeds(
                feed_urls=feed_urls,
                limit_per_feed=20,
                deduplicate=True
            )

            if articles:
                # Save to database
                async with AsyncSessionLocal() as db:
                    stats = await article_persistence_service.save_articles(
                        articles=articles,
                        db=db,
                        auto_approve=True
                    )

                    logger.info(
                        f"RSS fetch complete: Saved {stats['saved']}, "
                        f"Duplicates {stats['duplicates']}, "
                        f"Errors {stats['errors']}"
                    )

                    # Invalidate cache if new articles were saved
                    if stats['saved'] > 0:
                        logger.info(f"Invalidating article cache after saving {stats['saved']} RSS articles")
                        await invalidate_article_cache()
                        logger.info(" Article cache invalidated")

                    return {
                        'status': 'success',
                        'saved': stats['saved'],
                        'duplicates': stats['duplicates'],
                        'errors': stats['errors'],
                        'timestamp': datetime.now(timezone.utc).isoformat(),
                        'cache_invalidated': stats['saved'] > 0
                    }
            else:
                logger.info("No articles fetched from RSS feeds")
                return {
                    'status': 'success',
                    'saved': 0,
                    'duplicates': 0,
                    'errors': 0,
                    'timestamp': datetime.now(timezone.utc).isoformat(),
                    'cache_invalidated': False
                }

        finally:
            await redis_client.close()

    except Exception as e:
        logger.error(f"Error in RSS fetch: {e}", exc_info=True)
        raise


@celery_app.task(
    name='app.tasks.news_tasks.cleanup_old_articles',
    bind=True,
    autoretry_for=(Exception,),
    retry_kwargs={'max_retries': 2, 'countdown': 600}
)
def cleanup_old_articles(self, days_old: int = 90):
    return asyncio.run(_async_cleanup_old_articles(days_old))


async def _async_cleanup_old_articles(days_old: int = 90):
    try:
        from app.models.article import Article
        from app.core.database import AsyncSessionLocal
        from sqlalchemy import update

        logger.info(f"Celery Task: Cleaning up articles older than {days_old} days...")

        threshold_date = datetime.now(timezone.utc) - timedelta(days=days_old)

        async with AsyncSessionLocal() as db:
            # Deactivate old articles
            result = await db.execute(
                update(Article)
                .where(Article.published_date < threshold_date)
                .where(Article.is_active == True)
                .values(is_active=False, deleted_at=datetime.now(timezone.utc))
            )

            await db.commit()

            count = result.rowcount
            logger.info(f"Deactivated {count} old articles")

            return {
                'status': 'success',
                'deactivated': count,
                'threshold_date': threshold_date.isoformat(),
                'timestamp': datetime.now(timezone.utc).isoformat()
            }

    except Exception as e:
        logger.error(f"Error in cleanup task: {e}", exc_info=True)
        raise


@celery_app.task(
    name='app.tasks.news_tasks.fetch_news_manual',
    bind=True
)
def fetch_news_manual(
    self,
    query: Optional[str] = None,
    sources: Optional[List[str]] = None,
    limit: int = 50
):
    return asyncio.run(_async_fetch_news_manual(query, sources, limit))


async def _async_fetch_news_manual(
    query: Optional[str] = None,
    sources: Optional[List[str]] = None,
    limit: int = 50
):
    try:
        from app.services.news_aggregator import NewsAggregatorService
        from app.services.article_persistence import article_persistence_service
        from app.core.database import AsyncSessionLocal
        from app.dependencies.cache import invalidate_article_cache
        from app.core.cache import init_cache_manager
        import redis.asyncio as aioredis

        logger.info(f"Manual fetch triggered for query: {query}")

        # Connect to Redis
        redis_client = aioredis.from_url(
            settings.REDIS_URL,
            encoding="utf-8",
            decode_responses=True
        )

        try:
            # Initialize cache manager (sets up global singleton for cache invalidation)
            init_cache_manager(
                redis_client,
                default_ttl=settings.REDIS_CACHE_TTL,
                compression_threshold=1024,
                key_prefix="news_app"
            )

            # Create aggregator
            aggregator = NewsAggregatorService(
                redis_client=redis_client,
                newsapi_key=settings.NEWS_API_KEY,
                cache_ttl=settings.NEWS_CACHE_TTL
            )

            # Fetch articles (bypass cache for manual fetches to get latest data)
            articles = await aggregator.aggregate_news(
                query=query,
                sources=sources,
                limit=limit,
                deduplicate=True,
                use_cache=False,
                topics=[query] if query else None
            )

            if articles:
                async with AsyncSessionLocal() as db:
                    stats = await article_persistence_service.save_articles(
                        articles=articles,
                        db=db,
                        auto_approve=True
                    )

                    # Invalidate cache if new articles were saved
                    if stats.get('saved', 0) > 0:
                        logger.info(f"Invalidating article cache after manual fetch saved {stats['saved']} articles")
                        await invalidate_article_cache()
                        logger.info(" Article cache invalidated")

                    return {
                        'status': 'success',
                        'statistics': stats,
                        'timestamp': datetime.now(timezone.utc).isoformat(),
                        'cache_invalidated': stats.get('saved', 0) > 0
                    }
            else:
                return {
                    'status': 'success',
                    'statistics': {'total': 0, 'saved': 0, 'duplicates': 0, 'errors': 0},
                    'message': 'No articles found',
                    'timestamp': datetime.now(timezone.utc).isoformat(),
                    'cache_invalidated': False
                }

        finally:
            await redis_client.close()

    except Exception as e:
        logger.error(f"Error in manual fetch: {e}", exc_info=True)
        raise

