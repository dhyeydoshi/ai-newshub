"""
News Aggregation Service
Complete implementation with multiple sources, caching, and security
"""
from abc import ABC, abstractmethod
from typing import List, Dict, Any, Optional, Set, Union
from datetime import datetime, timezone
import asyncio
import hashlib
import re
from urllib.parse import urlparse
import httpx
import feedparser
from bs4 import BeautifulSoup
import redis.asyncio as aioredis
from tenacity import (
    retry,
    stop_after_attempt,
    wait_exponential,
    retry_if_exception_type
)
import logging
import json

from app.utils.date_parser import parse_iso_date, parse_gdelt_date, parse_rss_date

logger = logging.getLogger(__name__)


# ============================================================================
# CIRCUIT BREAKER PATTERN
# ============================================================================

class CircuitBreaker:
    """Circuit breaker pattern implementation for API failures"""
    
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
        self.state = "closed"  # closed, open, half-open
    
    def call(self, func, *args, **kwargs):
        """Execute function with circuit breaker protection"""
        if self.state == "open":
            if self._should_attempt_reset():
                self.state = "half-open"
                logger.info(f"Circuit breaker half-open for {func.__name__}")
            else:
                raise Exception(f"Circuit breaker is OPEN for {func.__name__}")
        
        try:
            result = func(*args, **kwargs)
            self._on_success()
            return result
        except self.expected_exception as e:
            self._on_failure()
            raise e
    
    async def async_call(self, func, *args, **kwargs):
        """Async version of circuit breaker call"""
        if self.state == "open":
            if self._should_attempt_reset():
                self.state = "half-open"
                logger.info(f"Circuit breaker half-open for {func.__name__}")
            else:
                raise Exception(f"Circuit breaker is OPEN for {func.__name__}")
        
        try:
            result = await func(*args, **kwargs)
            self._on_success()
            return result
        except self.expected_exception as e:
            self._on_failure()
            raise e
    
    def _on_success(self):
        """Reset on successful call"""
        self.failure_count = 0
        self.state = "closed"
    
    def _on_failure(self):
        """Increment failure count and open if threshold reached"""
        self.failure_count += 1
        self.last_failure_time = datetime.now(timezone.utc)
        
        if self.failure_count >= self.failure_threshold:
            self.state = "open"
            logger.error(f"Circuit breaker OPENED after {self.failure_count} failures")
    
    def _should_attempt_reset(self) -> bool:
        """Check if enough time has passed to attempt reset"""
        if not self.last_failure_time:
            return True
        
        time_since_failure = (datetime.now(timezone.utc) - self.last_failure_time).total_seconds()
        return time_since_failure >= self.timeout


# ============================================================================
# CONTENT SANITIZER
# ============================================================================

class ContentSanitizer:
    """Sanitize and validate content from external sources"""
    
    # Dangerous HTML tags and attributes
    DANGEROUS_TAGS = {
        'script', 'iframe', 'object', 'embed', 'link', 'style',
        'meta', 'base', 'form', 'input', 'button'
    }
    
    DANGEROUS_ATTRIBUTES = {
        'onclick', 'onload', 'onerror', 'onmouseover', 'onmouseout',
        'onfocus', 'onblur', 'onchange', 'onsubmit'
    }

    ALLOWED_TAGS = {
        'p', 'br', 'strong', 'em', 'u', 'h1', 'h2', 'h3', 'h4', 'h5', 'h6',
        'ul', 'ol', 'li', 'blockquote', 'a', 'img', 'div', 'span', 'pre', 'html', 'body'
    }

    ALLOWED_ATTRIBUTES = {
        'href', 'src', 'alt', 'title', 'class'
    }

    @classmethod
    def sanitize_html(cls, html: str) -> str:
        """Remove dangerous HTML tags and attributes"""
        if not html:
            return ""
        
        try:
            soup = BeautifulSoup(html, 'lxml')

            # Remove dangerous tags
            for tag in soup.find_all():
                if tag.name in cls.DANGEROUS_TAGS:
                    tag.decompose()
                    continue
                elif tag.name in cls.ALLOWED_TAGS:
                    tag.unwrap()
                    continue
                
                # Remove dangerous attributes
                attrs_to_remove = []
                for attr in tag.attrs:
                    if attr.lower() in cls.DANGEROUS_ATTRIBUTES:
                        attrs_to_remove.append(attr)
                    elif attr.lower().startswith('on'):  # All event handlers
                        attrs_to_remove.append(attr)
                
                for attr in attrs_to_remove:
                    del tag[attr]
                
                # Sanitize href and src attributes
                if 'href' in tag.attrs:
                    tag['href'] = cls._sanitize_url(tag['href'])
                if 'src' in tag.attrs:
                    tag['src'] = cls._sanitize_url(tag['src'])
            
            return str(soup)
        except Exception as e:
            logger.error(f"Error sanitizing HTML: {e}")
            return BeautifulSoup(html, 'html.parser').get_text()
    
    @classmethod
    def sanitize_text(cls, text: str) -> str:
        """Remove any HTML/script content from text"""
        if not text:
            return ""
        
        # Remove HTML tags
        text = BeautifulSoup(text, 'html.parser').get_text()
        
        # Remove excessive whitespace
        text = re.sub(r'\s+', ' ', text).strip()
        
        return text
    
    @classmethod
    def _sanitize_url(cls, url: str) -> str:
        """Validate and sanitize URLs"""
        if not url:
            return ""
        
        # Remove javascript: and data: URLs
        if url.lower().startswith(('javascript:', 'data:', 'vbscript:')):
            return ""
        
        # Validate URL format
        try:
            parsed = urlparse(url)
            if parsed.scheme not in ['http', 'https', '']:
                return ""
            return url
        except Exception:
            return ""
    
    @classmethod
    def validate_article_data(cls, data: Dict[str, Any]) -> Dict[str, Any]:
        """Validate and sanitize article data"""
        validated = {}
        
        # Required fields
        validated['title'] = cls.sanitize_text(data.get('title', ''))[:500]
        validated['content'] = cls.sanitize_html(data.get('content', ''))[:50000]
        validated['url'] = cls._sanitize_url(data.get('url', ''))[:2048]
        
        # Optional fields
        if 'description' in data:
            validated['description'] = cls.sanitize_text(data.get('description', ''))[:1000]
        
        if 'author' in data:
            validated['author'] = cls.sanitize_text(data.get('author', ''))[:255]
        
        if 'source' in data:
            validated['source'] = cls.sanitize_text(data.get('source', ''))[:255]
        
        if 'published_date' in data:
            validated['published_date'] = data.get('published_date')
        
        if 'image_url' in data:
            validated['image_url'] = cls._sanitize_url(data.get('image_url', ''))[:2048]
        
        # Validate required fields are not empty
        if not validated['title'] or not validated['url']:
            raise ValueError("Article must have title and URL")
        
        return validated


# ============================================================================
# DEDUPLICATION ALGORITHM
# ============================================================================

class ArticleDeduplicator:
    """Deduplicate articles using content similarity"""
    
    @staticmethod
    def generate_content_hash(content: str) -> str:
        """Generate hash for content deduplication"""
        # Normalize content
        normalized = re.sub(r'\s+', ' ', content.lower().strip())
        # Generate SHA-256 hash
        return hashlib.sha256(normalized.encode()).hexdigest()
    
    @staticmethod
    def calculate_similarity(text1: str, text2: str) -> float:
        """Calculate Jaccard similarity between two texts"""
        if not text1 or not text2:
            return 0.0
        
        # Tokenize and create sets
        words1 = set(re.findall(r'\w+', text1.lower()))
        words2 = set(re.findall(r'\w+', text2.lower()))
        
        if not words1 or not words2:
            return 0.0
        
        # Jaccard similarity
        intersection = len(words1 & words2)
        union = len(words1 | words2)
        
        return intersection / union if union > 0 else 0.0
    
    @classmethod
    def deduplicate_articles(
        cls,
        articles: List[Dict[str, Any]],
        similarity_threshold: float = 0.8
    ) -> List[Dict[str, Any]]:
        """Remove duplicate articles based on content similarity"""
        if not articles:
            return []
        
        unique_articles = []
        seen_hashes: Set[str] = set()
        
        for article in articles:
            # Generate content hash
            content = article.get('content', '') or article.get('description', '')
            content_hash = cls.generate_content_hash(content)
            
            # Check if exact duplicate
            if content_hash in seen_hashes:
                logger.debug(f"Skipping duplicate article: {article.get('title', 'Unknown')}")
                continue
            
            # Check similarity with existing articles
            is_duplicate = False
            for existing in unique_articles:
                existing_content = existing.get('content', '') or existing.get('description', '')
                similarity = cls.calculate_similarity(content, existing_content)
                
                if similarity >= similarity_threshold:
                    logger.debug(
                        f"Skipping similar article (similarity: {similarity:.2f}): "
                        f"{article.get('title', 'Unknown')}"
                    )
                    is_duplicate = True
                    break
            
            if not is_duplicate:
                seen_hashes.add(content_hash)
                article['content_hash'] = content_hash
                unique_articles.append(article)
        
        logger.info(f"Deduplicated {len(articles)} articles to {len(unique_articles)} unique articles")
        return unique_articles


# ============================================================================
# BASE FETCHER ABSTRACT CLASS
# ============================================================================

class BaseFetcher(ABC):
    """Abstract base class for news fetchers"""
    
    def __init__(
        self,
        api_key: Optional[str] = None,
        timeout: int = 5,
        max_retries: int = 3
    ):
        self.api_key = api_key
        self.timeout = timeout
        self.max_retries = max_retries
        self.circuit_breaker = CircuitBreaker(failure_threshold=5, timeout=60)
        self.sanitizer = ContentSanitizer()
    
    @abstractmethod
    async def fetch_articles(
        self,
        query: Optional[str] = None,
        limit: int = 20,
        **kwargs
    ) -> List[Dict[str, Any]]:
        """Fetch articles from source"""
        pass
    
    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=10),
        retry=retry_if_exception_type((httpx.TimeoutException, httpx.NetworkError))
    )
    async def _make_request(
        self,
        url: str,
        params: Optional[Dict] = None,
        headers: Optional[Dict] = None
    ) -> httpx.Response:
        """Make HTTP request with retry logic"""
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            response = await client.get(url, params=params, headers=headers)
            response.raise_for_status()
            return response
    
    def _validate_and_sanitize(self, article: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Validate and sanitize article data"""
        try:
            return self.sanitizer.validate_article_data(article)
        except ValueError as e:
            logger.warning(f"Invalid article data: {e}")
            return None


# ============================================================================
# NEWSAPI FETCHER
# ============================================================================

class NewsAPIFetcher(BaseFetcher):
    """Fetch news from NewsAPI.org"""
    
    BASE_URL = "https://newsapi.org/v2"
    
    async def fetch_articles(
        self,
        query: Optional[str] = None,
        limit: int = 20,
        category: Optional[str] = None,
        language: str = "en",
        **kwargs
    ) -> List[Dict[str, Any]]:
        """Fetch articles from NewsAPI"""
        if not self.api_key:
            logger.warning("NewsAPI key not configured")
            return []
        
        try:
            # Build parameters
            params = {
                'apiKey': self.api_key,
                'pageSize': min(limit, 100),
                'language': language
            }
            
            # Use top-headlines or everything endpoint
            if category:
                endpoint = f"{self.BASE_URL}/top-headlines"
                params['category'] = category
            else:
                endpoint = f"{self.BASE_URL}/everything"
                params['sortBy'] = 'publishedAt'
            
            if query:
                params['q'] = query
            
            # Make request with circuit breaker
            response = await self.circuit_breaker.async_call(
                self._make_request,
                endpoint,
                params=params
            )
            
            data = response.json()
            
            if data.get('status') != 'ok':
                logger.error(f"NewsAPI error: {data.get('message', 'Unknown error')}")
                return []
            
            # Process articles
            articles = []
            for item in data.get('articles', []):
                article = self._normalize_newsapi_article(item)
                validated = self._validate_and_sanitize(article)
                if validated:
                    articles.append(validated)
            
            logger.info(f"Fetched {len(articles)} articles from NewsAPI")
            return articles
            
        except Exception as e:
            logger.error(f"Error fetching from NewsAPI: {e}")
            return []
    
    def _normalize_newsapi_article(self, item: Dict) -> Dict[str, Any]:
        """Normalize NewsAPI article format"""
        return {
            'title': item.get('title', ''),
            'content': item.get('content', '') or item.get('description', ''),
            'description': item.get('description', ''),
            'url': item.get('url', ''),
            'source': item.get('source', {}).get('name', 'NewsAPI'),
            'author': item.get('author', ''),
            'published_date': parse_iso_date(item.get('publishedAt')),
            'image_url': item.get('urlToImage', ''),
            'metadata': {
                'source_id': item.get('source', {}).get('id', '')
            }
        }
    
    @staticmethod
    def _parse_date(date_str: Optional[str]) -> datetime:
        """Parse ISO date string"""
        if not date_str:
            return datetime.now(timezone.utc)
        try:
            return datetime.fromisoformat(date_str.replace('Z', '+00:00'))
        except Exception:
            return datetime.now(timezone.utc)


# ============================================================================
# GDELT FETCHER
# ============================================================================

class GDELTFetcher(BaseFetcher):
    """Fetch news from GDELT Project"""

    BASE_URL = "https://api.gdeltproject.org/api/v2/doc/doc"

    async def fetch_articles(
        self,
        query: Optional[str] = None,
        limit: int = 20,
        **kwargs
    ) -> List[Dict[str, Any]]:
        """Fetch articles from GDELT"""
        if not query:
            query = "news"  # Default query

        try:
            params = {
                'query': query,
                'mode': 'artlist',
                'maxrecords': min(limit, 250),
                'format': 'json',
                'sort': 'hybridrel'
            }

            # Make request with circuit breaker
            response = await self.circuit_breaker.async_call(
                self._make_request,
                self.BASE_URL,
                params=params
            )

            data = response.json()

            # Process articles
            articles = []
            for item in data.get('articles', []):
                article = self._normalize_gdelt_article(item)
                validated = self._validate_and_sanitize(article)
                if validated:
                    articles.append(validated)

            logger.info(f"Fetched {len(articles)} articles from GDELT")
            return articles

        except Exception as e:
            logger.error(f"Error fetching from GDELT: {e}")
            return []

    def _normalize_gdelt_article(self, item: Dict) -> Dict[str, Any]:
        """Normalize GDELT article format"""
        return {
            'title': item.get('title', ''),
            'content': item.get('seendate', ''),  # GDELT doesn't provide full content
            'description': item.get('title', ''),
            'url': item.get('url', ''),
            'source': item.get('domain', 'GDELT'),
            'author': '',
            'published_date': parse_gdelt_date(item.get('seendate')),
            'image_url': item.get('socialimage', ''),
            'metadata': {
                'language': item.get('language', ''),
                'tone': item.get('tone', '')
            }
        }

    @staticmethod
    def _parse_gdelt_date(date_str: Optional[str]) -> datetime:
        """Parse GDELT date format (YYYYMMDDHHmmSS)"""
        if not date_str:
            return datetime.now(timezone.utc)
        try:
            return datetime.strptime(date_str, '%Y%m%d%H%M%S').replace(tzinfo=timezone.utc)
        except Exception:
            return datetime.now(timezone.utc)


# ============================================================================
# RSS FETCHER
# ============================================================================

class RSSFetcher(BaseFetcher):
    """Fetch news from RSS feeds"""

    async def fetch_articles(
        self,
        query: Optional[str] = None,
        limit: int = 20,
        feed_url: Optional[str] = None,
        **kwargs
    ) -> List[Dict[str, Any]]:
        """Fetch articles from RSS feed"""
        # feed_url can come from query parameter or kwargs
        url = feed_url or query

        if not url:
            logger.warning("No RSS feed URL provided")
            return []

        try:
            # Fetch RSS feed
            response = await self.circuit_breaker.async_call(
                self._make_request,
                url,
                headers={'User-Agent': 'NewsAggregator/1.0'}
            )

            # Parse feed
            feed = feedparser.parse(response.text)

            # Process entries
            articles = []
            for entry in feed.entries[:limit]:
                article = self._normalize_rss_entry(entry, feed.feed)
                validated = self._validate_and_sanitize(article)
                if validated:
                    articles.append(validated)

            logger.info(f"Fetched {len(articles)} articles from RSS: {url}")
            return articles

        except Exception as e:
            logger.error(f"Error fetching RSS feed {url}: {e}")
            return []

    def _normalize_rss_entry(self, entry: Any, feed_info: Any) -> Dict[str, Any]:
        """Normalize RSS entry format"""
        # Get content
        content = ''
        if hasattr(entry, 'content'):
            content = entry.content[0].value
        elif hasattr(entry, 'summary'):
            content = entry.summary
        elif hasattr(entry, 'description'):
            content = entry.description

        return {
            'title': entry.get('title', ''),
            'content': content,
            'description': entry.get('summary', '')[:500],
            'url': entry.get('link', ''),
            'source': feed_info.get('title', 'RSS Feed'),
            'author': entry.get('author', ''),
            'published_date': parse_rss_date(entry),
            'image_url': self._extract_image_from_entry(entry),
            'metadata': {
                'tags': [tag.term for tag in entry.get('tags', [])]
            }
        }

    @staticmethod
    def _parse_rss_date(entry: Any) -> datetime:
        """Parse RSS date"""
        if hasattr(entry, 'published_parsed') and entry.published_parsed:
            from time import mktime
            return datetime.fromtimestamp(mktime(entry.published_parsed), tz=timezone.utc)
        elif hasattr(entry, 'updated_parsed') and entry.updated_parsed:
            from time import mktime
            return datetime.fromtimestamp(mktime(entry.updated_parsed), tz=timezone.utc)
        return datetime.now(timezone.utc)

    @staticmethod
    def _extract_image_from_entry(entry: Any) -> str:
        """Extract image URL from RSS entry"""
        # Try media content
        if hasattr(entry, 'media_content'):
            for media in entry.media_content:
                if media.get('medium') == 'image':
                    return media.get('url', '')

        # Try enclosures
        if hasattr(entry, 'enclosures'):
            for enclosure in entry.enclosures:
                if 'image' in enclosure.get('type', ''):
                    return enclosure.get('href', '')

        return ''


# ============================================================================
# CACHING LAYER
# ============================================================================

class NewsCacheManager:
    """Redis-based caching for news articles"""
    
    def __init__(self, redis_client: aioredis.Redis, ttl: int = 900):
        self.redis = redis_client
        self.ttl = ttl  # 15 minutes default
    
    async def get_cached_articles(self, cache_key: str) -> Optional[List[Dict[str, Any]]]:
        """Get cached articles"""
        try:
            cached = await self.redis.get(cache_key)
            if cached:
                logger.debug(f"Cache hit for key: {cache_key}")
                articles = json.loads(cached)
                for article in articles:
                    if 'published_date' in article and isinstance(article['published_date'], str):
                        try:
                            article['published_date'] = datetime.fromisoformat(article['published_date'])
                        except Exception:
                            article['published_date'] = datetime.now(timezone.utc)

                return articles
            return None
        except Exception as e:
            logger.error(f"Error getting from cache: {e}")
            return None
    
    async def cache_articles(
        self,
        cache_key: str,
        articles: List[Dict[str, Any]]
    ) -> bool:
        """Cache articles"""
        try:
            # Convert datetime objects to ISO format for JSON serialization
            serializable_articles = []
            for article in articles:
                article_copy = article.copy()
                if 'published_date' in article_copy and isinstance(article_copy['published_date'], datetime):
                    article_copy['published_date'] = article_copy['published_date'].isoformat()
                serializable_articles.append(article_copy)
            
            await self.redis.setex(
                cache_key,
                self.ttl,
                json.dumps(serializable_articles)
            )
            logger.debug(f"Cached {len(articles)} articles with key: {cache_key}")
            return True
        except Exception as e:
            logger.error(f"Error caching articles: {e}")
            return False
    
    @staticmethod
    def generate_cache_key(source: str, query: Optional[str] = None, **kwargs) -> str:
        """Generate cache key from parameters"""
        key_parts = [source]
        if query:
            key_parts.append(query)
        for k, v in sorted(kwargs.items()):
            key_parts.append(f"{k}:{v}")
        return f"news:{':'.join(key_parts)}"


# ============================================================================
# MAIN NEWS AGGREGATOR SERVICE
# ============================================================================

class NewsAggregatorService:
    """Main service for aggregating news from multiple sources"""
    
    def __init__(
        self,
        redis_client: aioredis.Redis,
        newsapi_key: Optional[str] = None,
        cache_ttl: int = 900
    ):
        self.cache_manager = NewsCacheManager(redis_client, ttl=cache_ttl)
        self.deduplicator = ArticleDeduplicator()
        
        # Initialize fetchers
        self.fetchers = {
            'newsapi': NewsAPIFetcher(api_key=newsapi_key),
            # 'gdelt': GDELTFetcher(),
            # 'rss': RSSFetcher()
        }
    
    async def aggregate_news(
        self,
        query: Optional[str] = None,
        sources: Optional[List[str]] = None,
        limit: int = 50,
        deduplicate: bool = True,
        use_cache: bool = True,
        **kwargs
    ) -> List[Dict[str, Any]]:
        """
        Aggregate news from multiple sources
        
        Args:
            query: Search query
            sources: List of sources to fetch from (None = all)
            limit: Maximum articles per source
            deduplicate: Remove duplicate articles
            use_cache: Use cached results
            **kwargs: Additional parameters for fetchers
            
        Returns:
            List of aggregated articles
        """
        # Generate cache key
        cache_key = self.cache_manager.generate_cache_key(
            source='all' if not sources else ','.join(sources),
            query=query,
            limit=limit,
            **kwargs
        )
        
        # Check cache
        if use_cache:
            cached = await self.cache_manager.get_cached_articles(cache_key)
            if cached:
                logger.info(f"Returning {len(cached)} cached articles")
                return cached
        
        # Determine which sources to use
        if not sources:
            sources = list(self.fetchers.keys())
        
        # Fetch from all sources concurrently
        tasks = []
        for source in sources:
            if source in self.fetchers:
                fetcher = self.fetchers[source]
                if source == 'rss' and 'feed_url' in kwargs:
                    task = fetcher.fetch_articles(
                        feed_url=kwargs['feed_url'],
                        limit=limit
                    )
                else:
                    task = fetcher.fetch_articles(
                        query=query,
                        limit=limit,
                        **kwargs
                    )
                tasks.append(task)
        
        # Wait for all fetches to complete
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        # Combine results
        all_articles = []
        for result in results:
            if isinstance(result, Exception):
                logger.error(f"Fetch error: {result}")
                continue
            if isinstance(result, list):
                all_articles.extend(result)
        
        # Deduplicate if requested
        if deduplicate and all_articles:
            all_articles = self.deduplicator.deduplicate_articles(all_articles)
        
        # Sort by published date
        all_articles.sort(
            key=lambda x: x.get('published_date', datetime.now(timezone.utc)),
            reverse=True
        )
        
        # Limit total articles
        all_articles = all_articles[:limit]
        
        # Cache results
        if use_cache and all_articles:
            await self.cache_manager.cache_articles(cache_key, all_articles)
        
        logger.info(f"Aggregated {len(all_articles)} articles from {len(sources)} sources")
        
        return all_articles
    
    async def fetch_from_rss_feeds(
        self,
        feed_urls: List[str],
        limit_per_feed: int = 10,
        deduplicate: bool = True
    ) -> List[Dict[str, Any]]:
        """
        Fetch articles from multiple RSS feeds
        
        Args:
            feed_urls: List of RSS feed URLs
            limit_per_feed: Max articles per feed
            deduplicate: Remove duplicates
            
        Returns:
            List of articles from all feeds
        """
        rss_fetcher = self.fetchers['rss']
        
        # Fetch from all feeds concurrently
        tasks = [
            rss_fetcher.fetch_articles(feed_url=feed_url, limit=limit_per_feed)
            for feed_url in feed_urls
        ]
        
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        # Combine results
        all_articles = []
        for result in results:
            if isinstance(result, Exception):
                logger.error(f"RSS fetch error: {result}")
                continue
            if isinstance(result, list):
                all_articles.extend(result)
        
        # Deduplicate
        if deduplicate and all_articles:
            all_articles = self.deduplicator.deduplicate_articles(all_articles)
        
        # Sort by date
        all_articles.sort(
            key=lambda x: x.get('published_date', datetime.now(timezone.utc)),
            reverse=True
        )
        
        logger.info(f"Fetched {len(all_articles)} articles from {len(feed_urls)} RSS feeds")
        
        return all_articles


# Global instance (initialized with Redis client)
news_aggregator: Optional[NewsAggregatorService] = None


def get_news_aggregator(redis_client: aioredis.Redis, newsapi_key: Optional[str] = None) -> NewsAggregatorService:
    """Get or create news aggregator instance"""
    global news_aggregator
    if news_aggregator is None:
        news_aggregator = NewsAggregatorService(redis_client, newsapi_key=newsapi_key)
    return news_aggregator
