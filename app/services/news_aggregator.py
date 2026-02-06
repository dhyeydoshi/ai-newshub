from abc import ABC, abstractmethod
from typing import List, Dict, Any, Optional, Set
from datetime import datetime, timezone
import asyncio
import hashlib
import re
import json
import httpx
import feedparser
import redis.asyncio as aioredis
from tenacity import (
    retry,
    stop_after_attempt,
    wait_exponential,
    retry_if_exception_type
)
import logging

from app.schemas.raw_article import RawArticle
from app.utils.date_parser import parse_iso_date, parse_gdelt_date, parse_rss_date
from config import settings

logger = logging.getLogger(__name__)


def _normalize_topic_values(values: Optional[List[str]]) -> List[str]:
    """Normalize topic values for consistent persistence and filtering."""
    if not values:
        return []

    normalized: List[str] = []
    seen = set()
    for value in values:
        topic = str(value or "").strip().lower()
        if not topic or topic in seen:
            continue
        seen.add(topic)
        normalized.append(topic[:100])
    return normalized


class CircuitBreaker:
    """Circuit breaker for API failure handling."""

    def __init__(
        self,
        failure_threshold: int = 5,
        timeout: int = 60,
        expected_exception: type = Exception
    ):
        self.failure_threshold = failure_threshold
        self.timeout = timeout
        self.expected_exception = expected_exception
        self.failure_count = 0
        self.last_failure_time: Optional[datetime] = None
        self.state = "closed"

    async def async_call(self, func, *args, **kwargs):
        """Execute async function with circuit breaker protection."""
        if self.state == "open":
            if self._should_attempt_reset():
                self.state = "half-open"
                logger.info(f"Circuit breaker half-open for {func.__name__}")
            else:
                raise Exception(f"Circuit breaker OPEN for {func.__name__}")

        try:
            result = await func(*args, **kwargs)
            self._on_success()
            return result
        except self.expected_exception as e:
            self._on_failure()
            raise e

    def _on_success(self):
        self.failure_count = 0
        self.state = "closed"

    def _on_failure(self):
        self.failure_count += 1
        self.last_failure_time = datetime.now(timezone.utc)
        if self.failure_count >= self.failure_threshold:
            self.state = "open"
            logger.error(f"Circuit breaker OPENED after {self.failure_count} failures")

    def _should_attempt_reset(self) -> bool:
        if not self.last_failure_time:
            return True
        elapsed = (datetime.now(timezone.utc) - self.last_failure_time).total_seconds()
        return elapsed >= self.timeout


class ArticleDeduplicator:
    """Deduplicate articles using content hash and similarity."""

    @staticmethod
    def generate_content_hash(content: str) -> str:
        """Generate SHA-256 hash for deduplication."""
        normalized = re.sub(r'\s+', ' ', content.lower().strip())
        return hashlib.sha256(normalized.encode()).hexdigest()

    @staticmethod
    def calculate_similarity(text1: str, text2: str) -> float:
        """Calculate Jaccard similarity between two texts."""
        if not text1 or not text2:
            return 0.0
        words1 = set(re.findall(r'\w+', text1.lower()))
        words2 = set(re.findall(r'\w+', text2.lower()))
        if not words1 or not words2:
            return 0.0
        intersection = len(words1 & words2)
        union = len(words1 | words2)
        return intersection / union if union > 0 else 0.0

    @classmethod
    def deduplicate(
        cls,
        articles: List[RawArticle],
        similarity_threshold: float = 0.8
    ) -> List[RawArticle]:
        """Remove duplicate articles based on content hash and similarity."""
        if not articles:
            return []

        unique: List[RawArticle] = []
        seen_hashes: Set[str] = set()

        for article in articles:
            # Check exact hash match
            if article.content_hash in seen_hashes:
                logger.debug(f"Skipping duplicate (hash): {article.title[:50]}")
                continue

            # Check similarity with existing articles
            is_duplicate = False
            article_text = article.content or article.description or ""
            
            for existing in unique:
                existing_text = existing.content or existing.description or ""
                if cls.calculate_similarity(article_text, existing_text) >= similarity_threshold:
                    logger.debug(f"Skipping duplicate (similar): {article.title[:50]}")
                    is_duplicate = True
                    break

            if not is_duplicate:
                seen_hashes.add(article.content_hash)
                unique.append(article)

        logger.info(f"Deduplicated {len(articles)} → {len(unique)} articles")
        return unique


class BaseFetcher(ABC):
    """Abstract base class for news fetchers."""

    def __init__(self, api_key: Optional[str] = None, timeout: int = 10):
        self.api_key = api_key
        self.timeout = timeout
        self.circuit_breaker = CircuitBreaker(failure_threshold=5, timeout=60)

    @abstractmethod
    async def fetch(self, query: Optional[str] = None, limit: int = 20, **kwargs) -> List[RawArticle]:
        """Fetch articles from source. Returns list of validated RawArticle objects."""
        pass

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=10),
        retry=retry_if_exception_type((httpx.TimeoutException, httpx.NetworkError))
    )
    async def _request(
        self,
        url: str,
        params: Optional[Dict] = None,
        headers: Optional[Dict] = None
    ) -> httpx.Response:
        """Make HTTP request with retry logic."""
        async with httpx.AsyncClient(
            timeout=self.timeout,
            trust_env=settings.HTTP_CLIENT_TRUST_ENV,
            follow_redirects=settings.HTTP_CLIENT_FOLLOW_REDIRECTS
        ) as client:
            response = await client.get(url, params=params, headers=headers)
            response.raise_for_status()
            return response

    def _to_article(self, data: Dict[str, Any]) -> Optional[RawArticle]:
        """Validate dict to RawArticle, returning None on validation failure."""
        try:
            return RawArticle.model_validate(data)
        except Exception as e:
            logger.debug(f"Article validation failed: {e}")
            return None


class NewsAPIFetcher(BaseFetcher):
    """Fetch news from NewsAPI.org"""

    BASE_URL = "https://newsapi.org/v2"

    async def fetch(
        self,
        query: Optional[str] = None,
        limit: int = 20,
        category: Optional[str] = None,
        language: str = "en",
        **kwargs
    ) -> List[RawArticle]:
        if not self.api_key:
            logger.warning("NewsAPI key not configured")
            return []

        try:
            params = {
                'apiKey': self.api_key,
                'pageSize': min(limit, 100),
                'language': language
            }

            endpoint = f"{self.BASE_URL}/top-headlines" if category else f"{self.BASE_URL}/everything"
            if category:
                params['category'] = category
            else:
                params['sortBy'] = 'publishedAt'
            if query:
                params['q'] = query

            response = await self.circuit_breaker.async_call(self._request, endpoint, params=params)
            data = response.json()

            if data.get('status') != 'ok':
                logger.error(f"NewsAPI error: {data.get('message', 'Unknown')}")
                return []

            topic_hints = _normalize_topic_values(kwargs.get('topic_hints') or [])
            if category:
                topic_hints = _normalize_topic_values(topic_hints + [category])

            articles = []
            for item in data.get('articles', []):
                article = self._to_article({
                    'title': item.get('title', ''),
                    'content': item.get('content') or item.get('description', ''),
                    'description': item.get('description', ''),
                    'url': item.get('url', ''),
                    'source': item.get('source', {}).get('name', 'NewsAPI'),
                    'author': item.get('author'),
                    'published_date': parse_iso_date(item.get('publishedAt')),
                    'image_url': item.get('urlToImage'),
                    'language': language,
                    'topics': topic_hints,
                    'metadata': {'source_id': item.get('source', {}).get('id', '')}
                })
                if article:
                    articles.append(article)

            logger.info(f"NewsAPI: fetched {len(articles)} articles")
            return articles

        except Exception as e:
            logger.error(f"NewsAPI fetch error: {e}")
            return []


class GDELTFetcher(BaseFetcher):
    """Fetch news from GDELT Project"""

    BASE_URL = "https://api.gdeltproject.org/api/v2/doc/doc"

    async def fetch(
        self,
        query: Optional[str] = None,
        limit: int = 20,
        **kwargs
    ) -> List[RawArticle]:
        search_query = query or "news"

        try:
            params = {
                'query': search_query,
                'mode': 'artlist',
                'maxrecords': min(limit, 250),
                'format': 'json',
                'sort': 'hybridrel'
            }

            response = await self.circuit_breaker.async_call(self._request, self.BASE_URL, params=params)
            data = response.json()

            topic_hints = _normalize_topic_values(kwargs.get('topic_hints') or [])

            articles = []
            for item in data.get('articles', []):
                article = self._to_article({
                    'title': item.get('title', ''),
                    'content': item.get('title', ''),  # GDELT doesn't provide full content
                    'description': item.get('title', ''),
                    'url': item.get('url', ''),
                    'source': item.get('domain', 'GDELT'),
                    'published_date': parse_gdelt_date(item.get('seendate')),
                    'image_url': item.get('socialimage'),
                    'topics': topic_hints,
                    'metadata': {
                        'language': item.get('language', ''),
                        'tone': item.get('tone', '')
                    }
                })
                if article:
                    articles.append(article)

            logger.info(f"GDELT: fetched {len(articles)} articles")
            return articles

        except Exception as e:
            logger.error(f"GDELT fetch error: {e}")
            return []


class RSSFetcher(BaseFetcher):
    """Fetch news from RSS feeds"""

    async def fetch(
        self,
        query: Optional[str] = None,
        limit: int = 20,
        feed_url: Optional[str] = None,
        **kwargs
    ) -> List[RawArticle]:
        url = feed_url or query
        if not url:
            logger.warning("No RSS feed URL provided")
            return []

        topic_hints = _normalize_topic_values(kwargs.get('topic_hints') or [])

        try:
            response = await self.circuit_breaker.async_call(
                self._request,
                url,
                headers={'User-Agent': 'NewsAggregator/1.0'}
            )

            feed = feedparser.parse(response.text)

            articles = []
            for entry in feed.entries[:limit]:
                # Extract content
                content = ''
                if hasattr(entry, 'content') and entry.content:
                    content = entry.content[0].value
                elif hasattr(entry, 'summary'):
                    content = entry.summary
                elif hasattr(entry, 'description'):
                    content = entry.description

                # Extract image
                image_url = self._extract_image(entry)

                # Extract tags
                tags = [tag.term for tag in entry.get('tags', [])] if hasattr(entry, 'tags') else []
                entry_topics = _normalize_topic_values(topic_hints + tags)

                article = self._to_article({
                    'title': entry.get('title', ''),
                    'content': content,
                    'description': entry.get('summary', '')[:500] if entry.get('summary') else '',
                    'url': entry.get('link', ''),
                    'source': feed.feed.get('title', 'RSS Feed') if hasattr(feed, 'feed') else 'RSS Feed',
                    'author': entry.get('author'),
                    'published_date': parse_rss_date(entry),
                    'image_url': image_url,
                    'topics': entry_topics,
                    'tags': tags
                })
                if article:
                    articles.append(article)

            logger.info(f"RSS ({url[:50]}...): fetched {len(articles)} articles")
            return articles

        except Exception as e:
            logger.error(f"RSS fetch error ({url}): {e}")
            return []

    @staticmethod
    def _extract_image(entry: Any) -> Optional[str]:
        """Extract image URL from RSS entry."""
        if hasattr(entry, 'media_content'):
            for media in entry.media_content:
                if media.get('medium') == 'image':
                    return media.get('url')
        if hasattr(entry, 'enclosures'):
            for enclosure in entry.enclosures:
                if 'image' in enclosure.get('type', ''):
                    return enclosure.get('href')
        return None


class NewsCacheManager:
    """Redis-based caching for aggregated articles."""

    def __init__(self, redis_client: aioredis.Redis, ttl: int = 900):
        self.redis = redis_client
        self.ttl = ttl

    async def get(self, cache_key: str) -> Optional[List[RawArticle]]:
        """Get cached articles."""
        try:
            cached = await self.redis.get(cache_key)
            if cached:
                logger.debug(f"Cache hit: {cache_key}")
                data = json.loads(cached)
                return [RawArticle.from_cache_dict(item) for item in data]
            return None
        except Exception as e:
            logger.error(f"Cache get error: {e}")
            return None

    async def set(self, cache_key: str, articles: List[RawArticle]) -> bool:
        """Cache articles."""
        try:
            data = [article.to_cache_dict() for article in articles]
            await self.redis.setex(cache_key, self.ttl, json.dumps(data))
            logger.debug(f"Cached {len(articles)} articles: {cache_key}")
            return True
        except Exception as e:
            logger.error(f"Cache set error: {e}")
            return False

    @staticmethod
    def build_key(source: str, query: Optional[str] = None, **kwargs) -> str:
        """Generate cache key."""
        parts = [source]
        if query:
            parts.append(query)
        for k, v in sorted(kwargs.items()):
            parts.append(f"{k}:{v}")
        return f"news:{':'.join(parts)}"


class NewsAggregatorService:
    """Aggregates news from multiple sources with caching and deduplication."""

    def __init__(
        self,
        redis_client: aioredis.Redis,
        newsapi_key: Optional[str] = None,
        cache_ttl: int = 900
    ):
        self.cache = NewsCacheManager(redis_client, ttl=cache_ttl)
        self.deduplicator = ArticleDeduplicator()

        self.fetchers: Dict[str, BaseFetcher] = {
            'newsapi': NewsAPIFetcher(api_key=newsapi_key),
            'gdelt': GDELTFetcher(),
            'rss': RSSFetcher()
        }

    @staticmethod
    def _normalize_feed_url(url: str) -> str:
        """Normalize feed URLs to improve topic mapping matches."""
        return (url or "").strip().rstrip("/").lower()

    def _topics_for_feed_url(self, feed_url: Optional[str]) -> List[str]:
        if not feed_url:
            return []

        normalized_feed_url = self._normalize_feed_url(feed_url)
        matched_topics: List[str] = []

        for topic, urls in settings.RSS_TOPIC_FEED_URLS.items():
            for mapped_url in urls:
                if self._normalize_feed_url(mapped_url) == normalized_feed_url:
                    matched_topics.append(topic)
                    break

        return _normalize_topic_values(matched_topics)

    async def aggregate_news(
        self,
        query: Optional[str] = None,
        sources: Optional[List[str]] = None,
        limit: int = 50,
        deduplicate: bool = True,
        use_cache: bool = True,
        **kwargs
    ) -> List[Dict[str, Any]]:
        topics = _normalize_topic_values(kwargs.get('topics') or [])

        cache_key = self.cache.build_key(
            source='all' if not sources else ','.join(sorted(sources)),
            query=query,
            limit=limit,
            topics=','.join(sorted(topics))
        )

        # Check cache
        if use_cache:
            cached = await self.cache.get(cache_key)
            if cached:
                logger.info(f"Returning {len(cached)} cached articles")
                return [a.to_persistence_dict() for a in cached]

        # Determine sources
        source_list = sources or list(self.fetchers.keys())

        # Build fetch tasks
        tasks = []
        for source in source_list:
            if source not in self.fetchers:
                continue

            fetcher = self.fetchers[source]

            if source == 'rss':
                feed_urls = kwargs.get('feed_urls', [])
                feed_url = kwargs.get('feed_url')
                if not feed_urls and topics:
                    feed_urls = settings.get_rss_feed_urls_for_topics(topics)
                if feed_urls:
                    for url in feed_urls:
                        rss_topic_hints = _normalize_topic_values(topics + self._topics_for_feed_url(url))
                        tasks.append(fetcher.fetch(feed_url=url, limit=limit, topic_hints=rss_topic_hints))
                elif feed_url:
                    rss_topic_hints = _normalize_topic_values(topics + self._topics_for_feed_url(feed_url))
                    tasks.append(fetcher.fetch(feed_url=feed_url, limit=limit, topic_hints=rss_topic_hints))
                elif query and query.startswith(('http://', 'https://')):
                    rss_topic_hints = _normalize_topic_values(topics + self._topics_for_feed_url(query))
                    tasks.append(fetcher.fetch(feed_url=query, limit=limit, topic_hints=rss_topic_hints))
                elif settings.ENABLE_RSS_FEEDS and settings.RSS_FEED_URLS:
                    for url in settings.RSS_FEED_URLS:
                        rss_topic_hints = _normalize_topic_values(topics + self._topics_for_feed_url(url))
                        tasks.append(fetcher.fetch(feed_url=url, limit=limit, topic_hints=rss_topic_hints))
            else:
                tasks.append(fetcher.fetch(query=query, limit=limit, topic_hints=topics, **kwargs))

        # Execute all fetches concurrently
        results = await asyncio.gather(*tasks, return_exceptions=True)

        # Collect articles
        all_articles: List[RawArticle] = []
        for result in results:
            if isinstance(result, Exception):
                logger.error(f"Fetch error: {result}")
                continue
            if isinstance(result, list):
                all_articles.extend(result)

        # Deduplicate
        if deduplicate and all_articles:
            all_articles = self.deduplicator.deduplicate(all_articles)

        # Sort by date (newest first)
        all_articles.sort(key=lambda a: a.published_date, reverse=True)

        # Limit results
        all_articles = all_articles[:limit]

        # Cache results
        if use_cache and all_articles:
            await self.cache.set(cache_key, all_articles)

        logger.info(f"Aggregated {len(all_articles)} articles from {len(source_list)} sources")
        return [a.to_persistence_dict() for a in all_articles]

    async def fetch_from_rss_feeds(
        self,
        feed_urls: List[str],
        limit_per_feed: int = 10,
        deduplicate: bool = True
    ) -> List[Dict[str, Any]]:
        """Fetch from multiple RSS feeds."""
        rss_fetcher = self.fetchers['rss']

        tasks = []
        for url in feed_urls:
            rss_topic_hints = self._topics_for_feed_url(url)
            tasks.append(
                rss_fetcher.fetch(feed_url=url, limit=limit_per_feed, topic_hints=rss_topic_hints)
            )

        results = await asyncio.gather(*tasks, return_exceptions=True)

        all_articles: List[RawArticle] = []
        for result in results:
            if isinstance(result, Exception):
                logger.error(f"RSS error: {result}")
                continue
            if isinstance(result, list):
                all_articles.extend(result)

        if deduplicate and all_articles:
            all_articles = self.deduplicator.deduplicate(all_articles)

        all_articles.sort(key=lambda a: a.published_date, reverse=True)

        logger.info(f"Fetched {len(all_articles)} articles from {len(feed_urls)} RSS feeds")
        return [a.to_persistence_dict() for a in all_articles]


_aggregator_instance: Optional[NewsAggregatorService] = None


def get_news_aggregator(
    redis_client: aioredis.Redis,
    newsapi_key: Optional[str] = None
) -> NewsAggregatorService:
    """Get or create singleton aggregator instance."""
    global _aggregator_instance
    if _aggregator_instance is None:
        _aggregator_instance = NewsAggregatorService(redis_client, newsapi_key=newsapi_key)
    return _aggregator_instance
