import json
import warnings
from typing import Annotated, Dict, List, Optional
from pydantic import Field, field_validator, model_validator, computed_field
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict
from functools import lru_cache
import secrets
from pathlib import Path
from urllib.parse import quote_plus
import logging
import base64
import hashlib

logger = logging.getLogger(__name__)


class Settings(BaseSettings):
    """Application settings with security configurations"""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore"
    )

    # Application
    APP_NAME: str = "News Central API"
    APP_VERSION: str = "1.0.0"
    ENVIRONMENT: str = Field(default="development", pattern="^(development|staging|production)$")
    DEBUG: bool = Field(
        default=False,
        description="Enable debug mode"
    )
    API_V1_PREFIX: str = "/api/v1"
    FRONTEND_URL: str = "http://localhost:8501"
    PASSWORD_MIN_LENGTH: int =  Field(
        default=8,
        description="Minimum password length for user accounts"
    )
    PASSWORD_REQUIRE_UPPERCASE: bool = Field(
        default=True,
        description="Require at least one uppercase letter in passwords"
    )
    PASSWORD_REQUIRE_LOWERCASE: bool = Field(
        default=True,
        description="Require at least one lowercase letter in passwords"
    )
    PASSWORD_REQUIRE_DIGIT: bool = Field(
        default=True,
        description="Require at least one digit in passwords"
    )
    PASSWORD_REQUIRE_SPECIAL: bool = Field(
        default=True,
        description="Require at least one special character in passwords"
    )
    MAX_ACTIVE_SESSIONS: int = Field(
        default=5,
        description="Maximum concurrent active sessions per user"
    )

    ARGON2_TIME_COST: int = 2
    ARGON2_MEMORY_COST: int = 65536  # 64 MB
    ARGON2_PARALLELISM: int = 4
    ARGON2_HASH_LENGTH: int = 32
    ARGON2_SALT_LENGTH: int = 16

    REDIS_URL: str = "redis://localhost:6379/0"
    REDIS_PASSWORD: str = Field(
        default="",
        description="Redis password. When set, automatically injected into REDIS_URL."
    )
    REDIS_MAX_CONNECTIONS: int = 50
    REDIS_CACHE_TTL: int = 900  # 15 minutes default cache TTL
    REDIS_KEY_PREFIX: str = Field(
        default="news_app",
        description="Application namespace prefix for Redis keys to avoid collisions"
    )
    CELERY_BROKER_URL: Optional[str] = Field(
        default=None,
        description="Celery broker URL (defaults to REDIS_URL)"
    )
    CELERY_RESULT_BACKEND: Optional[str] = Field(
        default=None,
        description="Celery result backend URL (defaults to broker URL)"
    )
    CELERY_HEARTBEAT_INTERVAL_SECONDS: int = Field(
        default=60,
        ge=30,
        le=300,
        description="Interval for runtime Celery heartbeat task"
    )
    CELERY_HEARTBEAT_TTL_SECONDS: int = Field(
        default=180,
        ge=60,
        le=900,
        description="Redis TTL for Celery heartbeat keys"
    )
    CELERY_HEARTBEAT_LOG_INTERVAL_SECONDS: int = Field(
        default=60,
        ge=30,
        le=600,
        description="API monitor interval for Celery heartbeat warnings"
    )

    SECRET_KEY: str = Field(
        default="",
        description="Main application secret key (min 32 chars)"
    )

    # JWT Configuration
    JWT_ALGORITHM: str = "RS256"
    JWT_PRIVATE_KEY: Optional[str] = Field(
        default=None,
        description="RSA private key for JWT signing (PEM format or file path)"
    )
    JWT_PUBLIC_KEY: Optional[str] = Field(
        default=None,
        description="RSA public key for JWT verification (PEM format or file path)"
    )
    JWT_PRIVATE_KEY_PATH: Optional[str] = Field(
        default="private_key.pem",
        description="Path to private key file if not provided inline"
    )
    JWT_PUBLIC_KEY_PATH: Optional[str] = Field(
        default="public_key.pem",
        description="Path to public key file if not provided inline"
    )
    ACCESS_TOKEN_EXPIRE_HOURS: int = Field(
        default=1,
        description="access token expiration time in hours"
    )
    REFRESH_TOKEN_EXPIRE_DAYS: int = 7
    MAX_LOGIN_ATTEMPTS: int = Field(
        default=5,
        description="Maximum failed login attempts before account lockout"
    )
    ACCOUNT_LOCKOUT_DURATION_MINUTES: int = Field(
        default=30,
        description="Lockout duration after too many failed login attempts"
    )
    PASSWORD_RESET_TOKEN_EXPIRE_HOURS: int = Field(
        default=1,
        description="Password reset token expiration time in hours"
    )

    # Password hashing
    BCRYPT_ROUNDS: int = 12

    # Email verification
    EMAIL_VERIFICATION_REQUIRED: bool = Field(
        default=True,
        description="email verification for new users"
    )
    EMAIL_VERIFICATION_TOKEN_EXPIRE_HOURS: int = 24

    # Cookie settings
    COOKIE_HTTPONLY: bool = True
    COOKIE_SAMESITE: str = "lax"

    @field_validator("SECRET_KEY")
    @classmethod
    def validate_secret_key(cls, v: str) -> str:
        """Ensure secret key is strong enough"""
        if not v:
            # Generate a secure random key if not provided
            generated_key = secrets.token_urlsafe(32)
            warnings.warn(
                "SECRET_KEY not set in .env - using generated key. "
                "This should be set permanently in production!",
                UserWarning
            )
            return generated_key
        if len(v) < 32:
            raise ValueError("SECRET_KEY must be at least 32 characters long")
        return v

    @model_validator(mode='after')
    def load_jwt_keys(self) -> 'Settings':
        """Load JWT keys from files if not provided inline"""

        # Load private key
        if not self.JWT_PRIVATE_KEY:
            private_key_path = Path(self.JWT_PRIVATE_KEY_PATH)
            if private_key_path.exists():
                try:
                    self.JWT_PRIVATE_KEY = private_key_path.read_text()
                    logger.info(f"Loaded JWT private key from {private_key_path}")
                except Exception as e:
                    warnings.warn(
                        f"Failed to load private key from {private_key_path}: {e}. "
                        "Run 'python generate_keys.py' to create keys.",
                        UserWarning
                    )
            elif self.ENVIRONMENT == "production":
                raise ValueError(
                    f"JWT_PRIVATE_KEY not set and {private_key_path} not found. "
                    "Run 'python generate_keys.py' to generate keys."
                )
            else:
                warnings.warn(
                    f"JWT_PRIVATE_KEY not found at {private_key_path}. "
                    "Authentication will not work. Run 'python generate_keys.py'.",
                    UserWarning
                )

        # Load public key
        if not self.JWT_PUBLIC_KEY:
            public_key_path = Path(self.JWT_PUBLIC_KEY_PATH)
            if public_key_path.exists():
                try:
                    self.JWT_PUBLIC_KEY = public_key_path.read_text()
                    logger.info(f"Loaded JWT public key from {public_key_path}")
                except Exception as e:
                    warnings.warn(
                        f"Failed to load public key from {public_key_path}: {e}",
                        UserWarning
                    )
            elif self.ENVIRONMENT == "production":
                raise ValueError(
                    f"JWT_PUBLIC_KEY not set and {public_key_path} not found. "
                    "Run 'python generate_keys.py' to generate keys."
                )

        # Validate keys are proper PEM format
        if self.JWT_PRIVATE_KEY:
            if not self.JWT_PRIVATE_KEY.strip().startswith("-----BEGIN"):
                raise ValueError(
                    "JWT_PRIVATE_KEY must be in PEM format "
                    "(should start with -----BEGIN PRIVATE KEY-----)"
                )

        if self.JWT_PUBLIC_KEY:
            if not self.JWT_PUBLIC_KEY.strip().startswith("-----BEGIN"):
                raise ValueError(
                    "JWT_PUBLIC_KEY must be in PEM format "
                    "(should start with -----BEGIN PUBLIC KEY-----)"
                )

        return self

    # CORS Settings
    CORS_ENABLED: bool = True
    CORS_ORIGINS: Annotated[List[str], NoDecode] = Field( default=["http://localhost:3000", "http://localhost:8080", "http://localhost:8501", "http://localhost:8000"]
                                     , description="List of allowed CORS origins")
    CORS_ALLOW_CREDENTIALS: bool = True
    CORS_ALLOW_METHODS: Annotated[List[str], NoDecode] = Field(
        default=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"]
    )
    CORS_ALLOW_HEADERS: Annotated[List[str], NoDecode] = Field(
        default=["Authorization", "Content-Type", "X-API-Key", "X-Integration-Key"]
    )
    CORS_MAX_AGE: int = 600

    @field_validator("CORS_ORIGINS", mode="before")
    @classmethod
    def parse_cors_origins(cls, v) -> List[str]:
        """Parse CORS origins from comma-separated string"""
        if isinstance(v, str):
            raw = v.strip()
            if not raw:
                return []
            try:
                parsed = json.loads(raw)
                if isinstance(parsed, list):
                    return [str(origin).strip() for origin in parsed if str(origin).strip()]
            except json.JSONDecodeError:
                pass
            return [origin.strip().strip("\"'") for origin in raw.split(",") if origin.strip()]
        return v

    @field_validator("CORS_ALLOW_METHODS", "CORS_ALLOW_HEADERS", mode="before")
    @classmethod
    def parse_cors_lists(cls, v) -> List[str]:
        if isinstance(v, str):
            raw = v.strip()
            if not raw:
                return []
            try:
                parsed = json.loads(raw)
                if isinstance(parsed, list):
                    return [str(item).strip() for item in parsed if str(item).strip()]
            except json.JSONDecodeError:
                pass
            return [item.strip().strip("\"'") for item in raw.split(",") if item.strip()]
        return v

    # API Security
    API_KEY_HEADER: str = "X-API-Key"
    INTEGRATION_KEY_HEADER: str = "X-Integration-Key"

    # Integration API configuration
    ENABLE_INTEGRATION_API: bool = Field(
        default=False,
        description="Enable per-user integration feeds and webhook delivery APIs"
    )
    ENABLE_INTEGRATION_DELIVERY: bool = Field(
        default=False,
        description="Enable asynchronous webhook batch delivery tasks"
    )

    # Security keys for integration secret encryption (Fernet compatible key)
    INTEGRATION_ENCRYPTION_KEY_CURRENT: Optional[str] = Field(
        default=None,
        description="Current encryption key for integration secrets (Fernet key)"
    )
    INTEGRATION_ENCRYPTION_KEY_PREVIOUS: Optional[str] = Field(
        default=None,
        description="Previous encryption key for seamless key rotation"
    )

    # Dev profile quotas
    INTEGRATION_MAX_API_KEYS_PER_USER: int = 20
    INTEGRATION_MAX_FEEDS_PER_USER: int = 20
    INTEGRATION_MAX_BUNDLES_PER_USER: int = 10
    INTEGRATION_MAX_FEEDS_PER_BUNDLE: int = 20
    INTEGRATION_MAX_WEBHOOKS_PER_USER: int = 10
    INTEGRATION_MIN_BATCH_INTERVAL_MINUTES: int = 5
    INTEGRATION_MAX_ITEMS_PER_BATCH: int = 30

    # Production strict quotas
    INTEGRATION_PROD_MAX_API_KEYS_PER_USER: int = 5
    INTEGRATION_PROD_MAX_FEEDS_PER_USER: int = 5
    INTEGRATION_PROD_MAX_BUNDLES_PER_USER: int = 5
    INTEGRATION_PROD_MAX_FEEDS_PER_BUNDLE: int = 10
    INTEGRATION_PROD_MAX_WEBHOOKS_PER_USER: int = 3
    INTEGRATION_PROD_MIN_BATCH_INTERVAL_MINUTES: int = 15
    INTEGRATION_PROD_MAX_ITEMS_PER_BATCH: int = 10

    INTEGRATION_DEFAULT_RATE_LIMIT_PER_HOUR: int = 1000
    INTEGRATION_WEBHOOK_TEST_RATE_LIMIT_PER_HOUR: int = 30
    INTEGRATION_FEED_CACHE_TTL: int = 900
    INTEGRATION_WEBHOOK_TIMEOUT_SECONDS: int = 5
    INTEGRATION_WEBHOOK_MAX_FAILURES: int = 5
    INTEGRATION_DELIVERY_RETENTION_DAYS: int = 30

    NEWSAPI_KEY: Optional[str] = Field(
        default=None,
        description="NewsAPI.org API key"
    )
    NEWSAPI_BASE_URL: str = "https://newsapi.org/v2"
    NEWSAPI_TIMEOUT: int = 5
    NEWSAPI_MAX_RETRIES: int = 3
    HTTP_CLIENT_TRUST_ENV: bool = Field(
        default=False,
        description="Allow HTTP client to use system proxy/TLS env vars (HTTP_PROXY, HTTPS_PROXY, etc.)"
    )
    HTTP_CLIENT_FOLLOW_REDIRECTS: bool = Field(
        default=True,
        description="Follow HTTP redirects when fetching external feeds/APIs"
    )

    # GDELT Configuration
    GDELT_BASE_URL: str = "https://api.gdeltproject.org/api/v2/doc/doc"
    GDELT_TIMEOUT: int = 5

    # News Aggregation Settings
    NEWS_CACHE_TTL: int = 900  # 15 minutes
    NEWS_DEDUPLICATION_THRESHOLD: float = 0.8  # 80% similarity threshold
    NEWS_CIRCUIT_BREAKER_THRESHOLD: int = 5
    NEWS_CIRCUIT_BREAKER_TIMEOUT: int = 60
    NEWS_MAX_ARTICLES_PER_SOURCE: int = 50

    # News Scheduler Configuration
    ENABLE_NEWS_SCHEDULER: bool = Field(
        default=True,
        description="Enable automatic news fetching scheduler"
    )
    NEWS_FETCH_INTERVAL_HOURS: int = Field(
        default=2,
        description="How often to fetch news (in hours)"
    )
    NEWS_API_KEY: Optional[str] = Field(
        default=None,
        description="NewsAPI.org API key (same as NEWSAPI_KEY)"
    )
    NEWS_SOURCES: Annotated[List[str], NoDecode] = Field(
        default=["newsapi", "gdelt"],
        description="News sources to fetch from"
    )
    NEWS_FETCH_QUERIES: Annotated[List[str], NoDecode] = Field(
        default=[
            "technology",
            "artificial intelligence",
            "business",
            "science",
            "health",
            "world news",
            "politics",
            "entertainment",
            "sports"
        ],
        description="Search queries for news fetching"
    )
    ENABLE_RSS_FEEDS: bool = Field(
        default=True,
        description="Enable RSS feed fetching"
    )
    RSS_FEED_URLS: Annotated[List[str], NoDecode] = Field(
        default=[
            "https://rss.nytimes.com/services/xml/rss/nyt/Technology.xml",
            "https://feeds.bbci.co.uk/news/technology/rss.xml",
            "https://www.wired.com/feed/rss",
            "https://techcrunch.com/feed/",
            "https://www.theverge.com/rss/index.xml"
        ],
        description="RSS feed URLs to fetch from"
    )
    RSS_TOPIC_FEED_URLS: Annotated[Dict[str, List[str]], NoDecode] = Field(
        default={
            "technology": [
                "https://rss.nytimes.com/services/xml/rss/nyt/Technology.xml",
                "https://feeds.bbci.co.uk/news/technology/rss.xml",
                "https://www.wired.com/feed/rss",
                "https://techcrunch.com/feed/",
                "https://www.theverge.com/rss/index.xml",
            ],
            "science": [
                "https://rss.nytimes.com/services/xml/rss/nyt/Science.xml",
                "https://feeds.bbci.co.uk/news/science_and_environment/rss.xml",
                "https://www.sciencedaily.com/rss/top/science.xml",
            ],
            "business": [
                "https://rss.nytimes.com/services/xml/rss/nyt/Business.xml",
                "https://feeds.bbci.co.uk/news/business/rss.xml",
                "https://www.cnbc.com/id/10001147/device/rss/rss.html",
            ],
            "politics": [
                "https://rss.nytimes.com/services/xml/rss/nyt/Politics.xml",
                "https://feeds.bbci.co.uk/news/politics/rss.xml",
            ],
            "health": [
                "https://rss.nytimes.com/services/xml/rss/nyt/Health.xml",
                "https://feeds.bbci.co.uk/news/health/rss.xml",
            ],
            "sports": [
                "https://rss.nytimes.com/services/xml/rss/nyt/Sports.xml",
                "https://feeds.bbci.co.uk/sport/rss.xml",
            ],
            "entertainment": [
                "https://rss.nytimes.com/services/xml/rss/nyt/Arts.xml",
                "https://feeds.bbci.co.uk/news/entertainment_and_arts/rss.xml",
            ],
            "world": [
                "https://rss.nytimes.com/services/xml/rss/nyt/World.xml",
                "https://feeds.bbci.co.uk/news/world/rss.xml",
            ],
        },
        description="Topic to RSS feed URL mapping used for topic-driven RSS ingestion",
    )

    @field_validator("NEWS_SOURCES", mode="before")
    @classmethod
    def parse_news_sources(cls, v) -> List[str]:
        """Parse news sources from comma-separated string"""
        if isinstance(v, str):
            raw = v.strip()
            if not raw:
                return []
            try:
                parsed = json.loads(raw)
                if isinstance(parsed, list):
                    return [str(source).strip() for source in parsed if str(source).strip()]
            except json.JSONDecodeError:
                pass
            return [source.strip().strip("\"'") for source in raw.split(",") if source.strip()]
        return v

    @field_validator("NEWS_FETCH_QUERIES", mode="before")
    @classmethod
    def parse_news_queries(cls, v) -> List[str]:
        """Parse news queries from comma-separated string"""
        if isinstance(v, str):
            raw = v.strip()
            if not raw:
                return []
            try:
                parsed = json.loads(raw)
                if isinstance(parsed, list):
                    return [str(query).strip() for query in parsed if str(query).strip()]
            except json.JSONDecodeError:
                pass
            return [query.strip().strip("\"'") for query in raw.split(",") if query.strip()]
        return v

    @field_validator("RSS_FEED_URLS", mode="before")
    @classmethod
    def parse_rss_urls(cls, v) -> List[str]:
        """Parse RSS URLs from comma-separated string"""
        if isinstance(v, str):
            raw = v.strip()
            if not raw:
                return []
            try:
                parsed = json.loads(raw)
                if isinstance(parsed, list):
                    return [str(url).strip() for url in parsed if str(url).strip()]
            except json.JSONDecodeError:
                pass
            return [url.strip().strip("\"'") for url in raw.split(",") if url.strip()]
        return v

    @field_validator("RSS_TOPIC_FEED_URLS", mode="before")
    @classmethod
    def parse_topic_rss_urls(cls, v) -> Dict[str, List[str]]:
        if isinstance(v, str):
            v = v.strip()
            if not v:
                return {}
            try:
                v = json.loads(v)
            except json.JSONDecodeError:
                return {}

        if not isinstance(v, dict):
            return {}

        normalized: Dict[str, List[str]] = {}
        for topic, urls in v.items():
            if not isinstance(topic, str):
                continue

            topic_key = topic.strip().lower()
            if not topic_key:
                continue

            if isinstance(urls, str):
                parsed_urls = [u.strip() for u in urls.split(",") if u.strip()]
            elif isinstance(urls, list):
                parsed_urls = [str(u).strip() for u in urls if str(u).strip()]
            else:
                continue

            if parsed_urls:
                normalized[topic_key] = parsed_urls

        return normalized

    def get_rss_feed_urls_for_topics(self, topics: Optional[List[str]]) -> List[str]:
        if not topics:
            return list(self.RSS_FEED_URLS)

        urls: List[str] = []
        seen = set()
        for topic in topics:
            topic_key = (topic or "").strip().lower()
            if not topic_key:
                continue
            for url in self.RSS_TOPIC_FEED_URLS.get(topic_key, []):
                if url and url not in seen:
                    seen.add(url)
                    urls.append(url)

        if urls:
            return urls
        return list(self.RSS_FEED_URLS)

    def get_all_rss_feed_urls(self) -> List[str]:
        all_urls: List[str] = []
        seen = set()

        for url in self.RSS_FEED_URLS:
            if url and url not in seen:
                seen.add(url)
                all_urls.append(url)

        for topic_urls in self.RSS_TOPIC_FEED_URLS.values():
            for url in topic_urls:
                if url and url not in seen:
                    seen.add(url)
                    all_urls.append(url)

        return all_urls

    @model_validator(mode='after')
    def set_news_api_key(self):
        """Set NEWS_API_KEY from NEWSAPI_KEY if not provided"""
        if not self.NEWS_API_KEY and self.NEWSAPI_KEY:
            self.NEWS_API_KEY = self.NEWSAPI_KEY
        return self

    @model_validator(mode='after')
    def set_celery_redis_urls(self):
        """Default Celery URLs to Redis URL when not explicitly set."""
        # Inject REDIS_PASSWORD into REDIS_URL when provided
        if self.REDIS_PASSWORD:
            from urllib.parse import urlparse, urlunparse, quote_plus
            parsed = urlparse(self.REDIS_URL)
            if not parsed.password:
                encoded_pw = quote_plus(self.REDIS_PASSWORD)
                netloc = f":{encoded_pw}@{parsed.hostname}"
                if parsed.port:
                    netloc += f":{parsed.port}"
                self.REDIS_URL = urlunparse(parsed._replace(netloc=netloc))

        if not self.CELERY_BROKER_URL:
            self.CELERY_BROKER_URL = self.REDIS_URL
        if not self.CELERY_RESULT_BACKEND:
            self.CELERY_RESULT_BACKEND = self.CELERY_BROKER_URL
        return self

    @property
    def integration_limits(self) -> Dict[str, int]:
        """Return environment-aware integration quotas."""
        if self.is_production:
            return {
                "max_api_keys_per_user": self.INTEGRATION_PROD_MAX_API_KEYS_PER_USER,
                "max_feeds_per_user": self.INTEGRATION_PROD_MAX_FEEDS_PER_USER,
                "max_bundles_per_user": self.INTEGRATION_PROD_MAX_BUNDLES_PER_USER,
                "max_feeds_per_bundle": self.INTEGRATION_PROD_MAX_FEEDS_PER_BUNDLE,
                "max_webhooks_per_user": self.INTEGRATION_PROD_MAX_WEBHOOKS_PER_USER,
                "min_batch_interval_minutes": self.INTEGRATION_PROD_MIN_BATCH_INTERVAL_MINUTES,
                "max_items_per_batch": self.INTEGRATION_PROD_MAX_ITEMS_PER_BATCH,
            }

        return {
            "max_api_keys_per_user": self.INTEGRATION_MAX_API_KEYS_PER_USER,
            "max_feeds_per_user": self.INTEGRATION_MAX_FEEDS_PER_USER,
            "max_bundles_per_user": self.INTEGRATION_MAX_BUNDLES_PER_USER,
            "max_feeds_per_bundle": self.INTEGRATION_MAX_FEEDS_PER_BUNDLE,
            "max_webhooks_per_user": self.INTEGRATION_MAX_WEBHOOKS_PER_USER,
            "min_batch_interval_minutes": self.INTEGRATION_MIN_BATCH_INTERVAL_MINUTES,
            "max_items_per_batch": self.INTEGRATION_MAX_ITEMS_PER_BATCH,
        }

    def get_integration_encryption_key(self) -> str:
        """Return encryption key for integration secrets (Fernet format)."""
        if self.INTEGRATION_ENCRYPTION_KEY_CURRENT:
            return self.INTEGRATION_ENCRYPTION_KEY_CURRENT.strip()

        # In production we require explicit key provisioning.
        if self.is_production:
            raise ValueError(
                "INTEGRATION_ENCRYPTION_KEY_CURRENT must be set when ENABLE_INTEGRATION_API is enabled in production."
            )

        # Dev fallback derived from SECRET_KEY for easier local setup.
        digest = hashlib.sha256(self.SECRET_KEY.encode("utf-8")).digest()
        return base64.urlsafe_b64encode(digest).decode("utf-8")

    RATE_LIMIT_ENABLED: bool = True
    RATE_LIMIT_PER_MINUTE: int = 100
    RATE_LIMIT_BURST: int = 20  # Burst allowance
    RATE_LIMIT_BACKOFF_BASE: float = 2.0  # Exponential backoff base
    RATE_LIMIT_MAX_VIOLATIONS: int = 5  # Max violations before extended ban
    RATE_LIMIT_BAN_DURATION_MINUTES: int = 60  # Ban duration after max violations

    TRUSTED_PROXY_COUNT: int = Field(
        default=0,
        description="Number of trusted reverse proxies in front of the app. "
                    "When > 0, X-Forwarded-For is parsed to extract the real client IP. "
                    "Set to 1 when behind nginx/traefik."
    )

    MAX_REQUEST_SIZE_MB: int = Field(default=1)
    ALLOWED_CONTENT_TYPES: Annotated[List[str], NoDecode] = [
        "application/json",
        "application/x-www-form-urlencoded",
        "multipart/form-data"
    ]

    @computed_field
    @property
    def max_request_size_bytes(self) -> int:
        """Convert MB to bytes for middleware"""
        return self.MAX_REQUEST_SIZE_MB * 1024 * 1024

    @field_validator("ALLOWED_CONTENT_TYPES", mode="before")
    @classmethod
    def parse_content_types(cls, v) -> List[str]:
        """Parse content types from JSON string or list"""
        if isinstance(v, str):
            try:
                return json.loads(v)
            except json.JSONDecodeError:
                return [ct.strip() for ct in v.split(",") if ct.strip()]
        return v

    @field_validator("REDIS_KEY_PREFIX")
    @classmethod
    def validate_redis_key_prefix(cls, v: str) -> str:
        value = (v or "").strip().strip(":")
        if not value:
            raise ValueError("REDIS_KEY_PREFIX must not be empty")
        return value

    ENABLE_HSTS: bool = True
    HSTS_MAX_AGE: int = 31536000  # 1 year
    ENABLE_CSP: bool = True
    CSP_POLICY: str = (
        "default-src 'self'; "
        "script-src 'self' 'unsafe-inline'; "
        "style-src 'self' 'unsafe-inline'; "
        "img-src 'self' data: https:; "
        "font-src 'self' data:;"
    )

    LOG_LEVEL: str = Field(default="INFO", pattern="^(DEBUG|INFO|WARNING|ERROR|CRITICAL)$")
    LOG_FILE: str = "logs/app.log"
    LOG_MAX_SIZE_MB: int = 10
    LOG_BACKUP_COUNT: int = 5
    LOG_REQUESTS: bool = Field(
        default=True,
        description="Enable request/response logging"
    )
    LOG_REQUEST_BODY: bool = Field(
        default=False,
        description="Include request body in logs (may contain sensitive data)"
    )
    LOG_RESPONSE_BODY: bool = Field(
        default=False,
        description="Include response body in logs"
    )

    @field_validator("LOG_LEVEL")
    @classmethod
    def validate_log_level(cls, v: str) -> str:
        """Ensure log level is valid"""
        return v.upper()


    UPLOAD_DIR: str = "uploads"
    MAX_UPLOAD_SIZE_MB: int = 10
    ALLOWED_EXTENSIONS: Annotated[List[str], NoDecode] = ["jpg", "jpeg", "png", "gif", "pdf", "txt", "csv"]

    @field_validator("ALLOWED_EXTENSIONS", mode="before")
    @classmethod
    def parse_allowed_extensions(cls, v) -> List[str]:
        """Parse allowed extensions from comma-separated string"""
        if isinstance(v, str):
            raw = v.strip()
            if not raw:
                return []
            try:
                parsed = json.loads(raw)
                if isinstance(parsed, list):
                    return [str(ext).strip().lstrip(".") for ext in parsed if str(ext).strip()]
            except json.JSONDecodeError:
                pass
            return [ext.strip().lstrip(".").strip("\"'") for ext in raw.split(",") if ext.strip()]
        return v

    EMAIL_DELIVERY_PROVIDER: str = Field(
        default="smtp",
        pattern="^(smtp|graph|graph_msa)$",
        description="Email delivery provider: smtp, graph (app-only), or graph_msa (personal mailbox delegated)"
    )
    EMAIL_REQUEST_TIMEOUT_SECONDS: int = Field(
        default=15,
        ge=1,
        le=60,
        description="Timeout for outbound email provider HTTP requests"
    )
    EMAIL_MAX_RETRIES: int = Field(
        default=2,
        ge=1,
        le=5,
        description="Maximum retry attempts for transient email provider failures"
    )

    GRAPH_TENANT_ID: Optional[str] = Field(
        default=None,
        description="Microsoft Entra tenant ID for Graph OAuth2 client credentials flow"
    )
    GRAPH_CLIENT_ID: Optional[str] = Field(
        default=None,
        description="Microsoft Entra application (client) ID for Graph email delivery"
    )
    GRAPH_CLIENT_SECRET: Optional[str] = Field(
        default=None,
        description="Microsoft Entra client secret for Graph email delivery"
    )
    GRAPH_SENDER_USER: Optional[str] = Field(
        default=None,
        description="Mailbox user principal name or user ID used for Graph /users/{id}/sendMail"
    )
    GRAPH_SCOPE: str = Field(
        default="https://graph.microsoft.com/.default",
        description="OAuth2 scope for Graph client credentials token request"
    )
    GRAPH_API_BASE_URL: str = Field(
        default="https://graph.microsoft.com/v1.0",
        description="Base URL for Microsoft Graph API"
    )
    GRAPH_AUTH_BASE_URL: str = Field(
        default="https://login.microsoftonline.com",
        description="Microsoft identity authority host"
    )
    GRAPH_SAVE_TO_SENT_ITEMS: bool = Field(
        default=True,
        description="Save Graph-delivered messages to Sent Items"
    )
    GRAPH_MSA_CLIENT_ID: Optional[str] = Field(
        default=None,
        description="Public client ID for Microsoft personal mailbox delegated auth (MSAL)"
    )
    GRAPH_MSA_AUTHORITY: str = Field(
        default="https://login.microsoftonline.com/consumers",
        description="Authority for Microsoft personal accounts (consumers/common)"
    )
    GRAPH_MSA_SCOPES: Annotated[List[str], NoDecode] = Field(
        default=["https://graph.microsoft.com/Mail.Send"],
        description="Delegated Graph scopes used with MSAL for personal mailbox sending"
    )
    GRAPH_MSA_TOKEN_CACHE_FILE: str = Field(
        default="secrets/graph_msa_token_cache.json",
        description="Path to persisted MSAL token cache for delegated personal mailbox auth"
    )
    GRAPH_MSA_AUTO_DEVICE_FLOW: bool = Field(
        default=False,
        description="Allow device-code bootstrap automatically when cache is missing"
    )

    SMTP_HOST: str = Field(
        default="smtp-mail.outlook.com",    
        description="SMTP server host for sending emails"
    )
    SMTP_PORT: int = Field(
        default=587,
        description="SMTP server port for sending emails"
    )
    SMTP_USER: Optional[str] = Field(
        default=None,
        description="SMTP username for sending emails"
    )
    SMTP_PASSWORD: Optional[str] = Field(
        default=None,
        description="SMTP password for sending emails"
    )
    SMTP_FROM_EMAIL: Optional[str] = Field(
        default=None,
        description="Email address used in the 'From' field when sending emails"    
    )
    SMTP_FROM_NAME: str = Field(
        default="News Central",
        description="Name used in the 'From' field when sending emails"
    )
    DEVELOPER_CONTACT_EMAIL: Optional[str] = Field(
        default=None,
        description="Destination email for frontend 'Let's connect' messages"
    )

    @field_validator("EMAIL_DELIVERY_PROVIDER")
    @classmethod
    def normalize_email_delivery_provider(cls, v: str) -> str:
        """Normalize provider string to lowercase for stable comparisons."""
        return v.strip().lower()

    @field_validator("GRAPH_MSA_SCOPES", mode="before")
    @classmethod
    def parse_graph_msa_scopes(cls, v) -> List[str]:
        """Parse Graph MSA scopes from JSON array or comma-separated text."""
        reserved_scopes = {"offline_access", "openid", "profile"}

        def normalize_scopes(items: List[str]) -> List[str]:
            cleaned = [str(scope).strip() for scope in items if str(scope).strip()]
            filtered = [scope for scope in cleaned if scope.lower() not in reserved_scopes]
            return filtered or ["https://graph.microsoft.com/Mail.Send"]

        if isinstance(v, str):
            raw = v.strip()
            if not raw:
                return ["https://graph.microsoft.com/Mail.Send"]
            try:
                parsed = json.loads(raw)
                if isinstance(parsed, list):
                    return normalize_scopes(parsed)
            except json.JSONDecodeError:
                pass
            return normalize_scopes([scope.strip().strip("\"'") for scope in raw.split(",") if scope.strip()])
        if isinstance(v, list):
            return normalize_scopes(v)
        return ["https://graph.microsoft.com/Mail.Send"]

    @field_validator(
        "SMTP_USER",
        "SMTP_FROM_EMAIL",
        "DEVELOPER_CONTACT_EMAIL",
        "GRAPH_TENANT_ID",
        "GRAPH_CLIENT_ID",
        "GRAPH_CLIENT_SECRET",
        "GRAPH_SENDER_USER",
        "GRAPH_MSA_CLIENT_ID",
        mode="before",
    )
    @classmethod
    def normalize_optional_email_values(cls, v: Optional[str]) -> Optional[str]:
        """Treat empty or 'none' env values as unset for optional email settings."""
        if v is None:
            return None
        if isinstance(v, str):
            cleaned = v.strip()
            if not cleaned or cleaned.lower() == "none":
                return None
            return cleaned
        return v

    @model_validator(mode='after')
    def set_developer_contact_email(self) -> 'Settings':
        """Apply SMTP email defaults for optional settings."""
        if not self.SMTP_FROM_EMAIL and self.SMTP_USER:
            self.SMTP_FROM_EMAIL = self.SMTP_USER
        if not self.DEVELOPER_CONTACT_EMAIL and self.SMTP_FROM_EMAIL:
            self.DEVELOPER_CONTACT_EMAIL = self.SMTP_FROM_EMAIL
        return self


    @property
    def cookie_secure(self) -> bool:
        """Secure cookies in production only"""
        return self.ENVIRONMENT == "production"

    @property
    def is_production(self) -> bool:
        """Check if running in production"""
        return self.ENVIRONMENT == "production"


    DB_USER: str = Field(
        default="postgres",
        description="Database username"
    )
    DB_PASSWORD: str = Field(
        default="",
        description="Database password"
    )
    DB_HOST: str = Field(
        default="localhost",
        description="Database host"
    )
    DB_PORT: int = Field(
        default=5432,
        description="Database port"
    )
    DB_NAME: str = Field(
        default="",
        description="Database name"
    )

    @property
    def DATABASE_URL(self) -> str:
        """Construct async database URL with encoded password"""
        encoded_password = quote_plus(self.DB_PASSWORD)
        return f"postgresql+asyncpg://{self.DB_USER}:{encoded_password}@{self.DB_HOST}:{self.DB_PORT}/{self.DB_NAME}"

    @property
    def database_url_sync(self) -> str:
        """Get synchronous database URL for Alembic"""
        encoded_password = quote_plus(self.DB_PASSWORD)
        # Double %% ONLY for Alembic's INI file parsing
        encoded_password = encoded_password.replace('%', '%%')
        return f"postgresql://{self.DB_USER}:{encoded_password}@{self.DB_HOST}:{self.DB_PORT}/{self.DB_NAME}"

    def validate_configuration(self) -> List[str]:
        issues = []

        # Check critical keys
        if self.ENVIRONMENT == "production":
            if not self.JWT_PRIVATE_KEY:
                issues.append("JWT_PRIVATE_KEY not configured for production")
            if not self.JWT_PUBLIC_KEY:
                issues.append("JWT_PUBLIC_KEY not configured for production")
            if len(self.SECRET_KEY) < 32:
                issues.append("SECRET_KEY too short for production")
            if not self.DB_PASSWORD:
                issues.append("DB_PASSWORD must be set in production")
            if not self.REDIS_PASSWORD:
                issues.append("REDIS_PASSWORD should be set in production")
            if not self.NEWSAPI_KEY:
                issues.append("NEWSAPI_KEY not set - news aggregation will be limited")
            if self.ENABLE_INTEGRATION_API and not self.INTEGRATION_ENCRYPTION_KEY_CURRENT:
                issues.append("INTEGRATION_ENCRYPTION_KEY_CURRENT is required for integration API in production")

        if self.ENABLE_INTEGRATION_DELIVERY and not self.ENABLE_INTEGRATION_API:
            issues.append("ENABLE_INTEGRATION_DELIVERY requires ENABLE_INTEGRATION_API=true")
        return issues


@lru_cache()
def get_settings() -> Settings:
    settings = Settings()
    issues = settings.validate_configuration()
    if issues:
        for issue in issues:
            logger.warning(f"Configuration issue: {issue}")
    return settings


# Export settings instance
settings = get_settings()


