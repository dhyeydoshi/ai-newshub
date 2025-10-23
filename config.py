"""
Configuration Management Module
Complete settings for security middleware
"""
import json
import warnings
from email.policy import default
from typing import List, Optional
from pydantic import Field, field_validator, model_validator, computed_field
from pydantic_settings import BaseSettings, SettingsConfigDict
from functools import lru_cache
import secrets
from pathlib import Path
from urllib.parse import quote_plus



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

    # ========================================================================
    # REDIS CONFIGURATION
    # ========================================================================
    REDIS_URL: str = "redis://localhost:6379/0"
    REDIS_MAX_CONNECTIONS: int = 50
    REDIS_CACHE_TTL: int = 900  # 15 minutes default cache TTL

    # ========================================================================
    # SECURITY CONFIGURATION
    # ========================================================================
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
                    print(f"✓ Loaded JWT private key from {private_key_path}")
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
                    print(f"✓ Loaded JWT public key from {public_key_path}")
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
            print([origin.strip() for origin in v.split(",") if origin.strip()])
            return [origin.strip() for origin in v.split(",") if origin.strip()]
        return v

    # API Security
    API_KEY_HEADER: str = "X-API-Key"

    # ========================================================================
    # NEWS AGGREGATION SERVICES
    # ========================================================================
    NEWSAPI_KEY: Optional[str] = Field(
        default=None,
        description="NewsAPI.org API key"
    )
    NEWSAPI_BASE_URL: str = "https://newsapi.org/v2"
    NEWSAPI_TIMEOUT: int = 5
    NEWSAPI_MAX_RETRIES: int = 3

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

    @model_validator(mode='after')
    def set_news_api_key(self):
        """Set NEWS_API_KEY from NEWSAPI_KEY if not provided"""
        if not self.NEWS_API_KEY and self.NEWSAPI_KEY:
            self.NEWS_API_KEY = self.NEWSAPI_KEY
        return self

    # ========================================================================
    # LLM SERVICE CONFIGURATION
    # ========================================================================
    OPENAI_API_KEY: Optional[str] = Field(
        default=None,
        description="OpenAI API key for GPT models"
    )
    OPENAI_MODEL: str = "gpt-4-turbo-preview"
    OPENAI_MAX_TOKENS: int = 500
    OPENAI_TEMPERATURE: float = 0.3

    ANTHROPIC_API_KEY: Optional[str] = Field(
        default=None,
        description="Anthropic API key for Claude models"
    )
    ANTHROPIC_MODEL: str = "claude-3-sonnet-20240229"

    LOCAL_LLM_URL: str = "http://localhost:11434"

    LLM_PROVIDER: str = Field(default="openai", pattern="^(openai|anthropic|local)$")

    # ========================================================================
    # RATE LIMITING CONFIGURATION
    # ========================================================================
    RATE_LIMIT_ENABLED: bool = True
    RATE_LIMIT_PER_MINUTE: int = 100
    RATE_LIMIT_BURST: int = 20  # Burst allowance
    RATE_LIMIT_BACKOFF_BASE: float = 2.0  # Exponential backoff base
    RATE_LIMIT_MAX_VIOLATIONS: int = 5  # Max violations before extended ban
    RATE_LIMIT_BAN_DURATION_MINUTES: int = 60  # Ban duration after max violations

    # ========================================================================
    # REQUEST VALIDATION CONFIGURATION
    # ========================================================================
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

    # ========================================================================
    # SECURITY HEADERS CONFIGURATION
    # ========================================================================
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

    # ========================================================================
    # LOGGING CONFIGURATION
    # ========================================================================
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


    # ========================================================================
    # FILE UPLOAD CONFIGURATION
    # ========================================================================
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

    # ========================================================================
    # EMAIL CONFIGURATION
    # ========================================================================
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

    # ========================================================================
    # TESTING
    # ========================================================================
    #TEST_DATABASE_URL: str = "postgresql+asyncpg://postgres:password@localhost:5432/news_summarizer_test"

    # ========================================================================
    # COMPUTED PROPERTIES
    # ========================================================================
    @property
    def cookie_secure(self) -> bool:
        """Secure cookies in production only"""
        return self.ENVIRONMENT == "production"

    @property
    def is_production(self) -> bool:
        """Check if running in production"""
        return self.ENVIRONMENT == "production"

    # ========================================================================
    # DATABASE CONFIGURATION
    # ========================================================================

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
        """
        Validate configuration and return list of warnings/issues
        Useful for startup checks
        """
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
            if not self.OPENAI_API_KEY and not self.ANTHROPIC_API_KEY:
                issues.append("No LLM API keys configured - summarization will not work")

        return issues



@lru_cache()
def get_settings() -> Settings:
    """
    Get cached settings instance
    Using lru_cache ensures we only load settings once
    """
    settings = Settings()
    issues = settings.validate_configuration()
    if issues:
        print("\n⚠️  Configuration Issues Found:")
        for issue in issues:
            print(f"  - {issue}")
        print()
    return settings


# Export settings instance
settings = get_settings()
