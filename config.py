import json
import warnings
from typing import Dict, List, Optional
from pydantic import Field, field_validator, model_validator, computed_field
from pydantic_settings import BaseSettings, SettingsConfigDict
from functools import lru_cache
import secrets
from pathlib import Path
from urllib.parse import quote_plus
import logging


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
    APP_NAME: str = "News Summarizer API"
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
    REDIS_MAX_CONNECTIONS: int = 50
    REDIS_CACHE_TTL: int = 900  # 15 minutes default cache TTL
    CELERY_BROKER_URL: Optional[str] = Field(
        default=None,
        description="Celery broker URL (defaults to REDIS_URL)"
    )
    CELERY_RESULT_BACKEND: Optional[str] = Field(
        default=None,
        description="Celery result backend URL (defaults to broker URL)"
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
        default=24,
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
        default=False,
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
    CORS_ORIGINS: List[str] = Field( default=["http://localhost:3000", "http://localhost:8080", "http://localhost:8501", "http://localhost:8000"]
                                     , description="List of allowed CORS origins")
    CORS_ALLOW_CREDENTIALS: bool = True
    CORS_ALLOW_METHODS: List[str] = Field(default=["*"])
    CORS_ALLOW_HEADERS: List[str] = Field(default=["*"])
    CORS_MAX_AGE: int = 600

    @field_validator("CORS_ORIGINS", mode="before")
    @classmethod
    def parse_cors_origins(cls, v) -> List[str]:
        """Parse CORS origins from comma-separated string"""
        if isinstance(v, str):
            return [origin.strip() for origin in v.split(",") if origin.strip()]
        return v

    # API Security
    API_KEY_HEADER: str = "X-API-Key"

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
    NEWS_SOURCES: List[str] = Field(
        default=["newsapi", "gdelt"],
        description="News sources to fetch from"
    )
    NEWS_FETCH_QUERIES: List[str] = Field(
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
    RSS_FEED_URLS: List[str] = Field(
        default=[
            "https://rss.nytimes.com/services/xml/rss/nyt/Technology.xml",
            "https://feeds.bbci.co.uk/news/technology/rss.xml",
            "https://www.wired.com/feed/rss",
            "https://techcrunch.com/feed/",
            "https://www.theverge.com/rss/index.xml"
        ],
        description="RSS feed URLs to fetch from"
    )
    RSS_TOPIC_FEED_URLS: Dict[str, List[str]] = Field(
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
            return [source.strip() for source in v.split(",") if source.strip()]
        return v

    @field_validator("NEWS_FETCH_QUERIES", mode="before")
    @classmethod
    def parse_news_queries(cls, v) -> List[str]:
        """Parse news queries from comma-separated string"""
        if isinstance(v, str):
            return [query.strip() for query in v.split(",") if query.strip()]
        return v

    @field_validator("RSS_FEED_URLS", mode="before")
    @classmethod
    def parse_rss_urls(cls, v) -> List[str]:
        """Parse RSS URLs from comma-separated string"""
        if isinstance(v, str):
            return [url.strip() for url in v.split(",") if url.strip()]
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
        if not self.CELERY_BROKER_URL:
            self.CELERY_BROKER_URL = self.REDIS_URL
        if not self.CELERY_RESULT_BACKEND:
            self.CELERY_RESULT_BACKEND = self.CELERY_BROKER_URL
        return self

    RATE_LIMIT_ENABLED: bool = True
    RATE_LIMIT_PER_MINUTE: int = 100
    RATE_LIMIT_BURST: int = 20  # Burst allowance
    RATE_LIMIT_BACKOFF_BASE: float = 2.0  # Exponential backoff base
    RATE_LIMIT_MAX_VIOLATIONS: int = 5  # Max violations before extended ban
    RATE_LIMIT_BAN_DURATION_MINUTES: int = 60  # Ban duration after max violations

    MAX_REQUEST_SIZE_MB: int = Field(default=1)
    ALLOWED_CONTENT_TYPES: List[str] = [
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
    ALLOWED_EXTENSIONS: List[str] = ["jpg", "jpeg", "png", "gif", "pdf", "txt", "csv"]

    @field_validator("ALLOWED_EXTENSIONS", mode="before")
    @classmethod
    def parse_allowed_extensions(cls, v) -> List[str]:
        """Parse allowed extensions from comma-separated string"""
        if isinstance(v, str):
            return [ext.strip() for ext in v.split(",")]
        return v

    SMTP_HOST: str = "smtp.gmail.com"
    SMTP_PORT: int = 587
    SMTP_USER: Optional[str] = Field(
        default=None,
        description="SMTP username for sending emails"
    )
    SMTP_PASSWORD: Optional[str] = Field(
        default=None,
        description="SMTP password for sending emails"
    )
    SMTP_FROM_EMAIL: str = "noreply@newssummarizer.com"
    SMTP_FROM_NAME: str = "News Summarizer"


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
            if not self.NEWSAPI_KEY:
                issues.append("NEWSAPI_KEY not set - news aggregation will be limited")
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


