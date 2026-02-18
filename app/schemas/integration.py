from datetime import datetime
from html import escape
import re
from typing import Any, Dict, List, Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, HttpUrl, field_validator, model_validator


def _sanitize_name(value: Optional[str], max_len: int = 100) -> str:
    text = escape((value or "").strip())
    text = re.sub(r"\s+", " ", text)
    return text[:max_len]


def _sanitize_token_list(values: Optional[List[str]], max_items: int) -> List[str]:
    if not values:
        return []
    cleaned: List[str] = []
    seen = set()
    for raw in values:
        token = escape(str(raw or "").strip().lower())
        token = re.sub(r"\s+", " ", token)
        if not token or token in seen:
            continue
        seen.add(token)
        cleaned.append(token[:100])
        if len(cleaned) >= max_items:
            break
    return cleaned


class APIKeyCreateRequest(BaseModel):
    name: str = Field(..., min_length=3, max_length=100)
    scopes: List[str] = Field(default_factory=lambda: ["feed:read"])
    expires_in_days: int = Field(default=365, ge=1, le=365)

    @field_validator("name")
    @classmethod
    def validate_name(cls, value: str) -> str:
        cleaned = _sanitize_name(value, max_len=100)
        if len(cleaned) < 3:
            raise ValueError("Name must be at least 3 characters long")
        return cleaned

    @field_validator("scopes", mode="before")
    @classmethod
    def validate_scopes(cls, value: Any) -> List[str]:
        if value is None:
            return ["feed:read"]
        if isinstance(value, str):
            value = [v.strip() for v in value.split(",") if v.strip()]
        scopes = _sanitize_token_list(list(value), max_items=10)
        return scopes or ["feed:read"]


class APIKeyCreateResponse(BaseModel):
    api_key: str
    key_id: UUID
    prefix: str
    name: str
    scopes: List[str]
    expires_at: Optional[datetime] = None
    message: str = "API key created. Save it now because it will not be shown again."


class APIKeyResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    key_id: UUID = Field(alias="api_key_id")
    prefix: str = Field(alias="key_prefix")
    name: str
    scopes: List[str]
    rate_limit_per_hour: int
    request_count: int
    last_used_at: Optional[datetime] = None
    is_active: bool
    created_at: datetime
    expires_at: Optional[datetime] = None


class APIKeyListResponse(BaseModel):
    total: int
    keys: List[APIKeyResponse]


class FeedFilters(BaseModel):
    topics: List[str] = Field(default_factory=list)
    exclude_topics: List[str] = Field(default_factory=list)
    categories: List[str] = Field(default_factory=list)
    keywords: List[str] = Field(default_factory=list)
    exclude_keywords: List[str] = Field(default_factory=list)
    sources: List[str] = Field(default_factory=list)
    exclude_sources: List[str] = Field(default_factory=list)
    language: str = Field(default="en", max_length=10)
    exclude_read: bool = Field(default=True)
    min_score: float = Field(default=0.0, ge=0.0, le=1.0)
    max_age_days: int = Field(default=7, ge=1, le=30)
    limit: int = Field(default=20, ge=1, le=100)
    sort_mode: str = Field(default="date")

    @field_validator(
        "topics",
        "exclude_topics",
        "categories",
        "keywords",
        "exclude_keywords",
        "sources",
        "exclude_sources",
        mode="before",
    )
    @classmethod
    def sanitize_list_field(cls, value: Any) -> List[str]:
        if value is None:
            return []
        if isinstance(value, str):
            value = [v.strip() for v in value.split(",") if v.strip()]
        return _sanitize_token_list(list(value), max_items=50)

    @field_validator("language")
    @classmethod
    def normalize_language(cls, value: str) -> str:
        lang = escape(value.strip().lower())
        return lang[:10] if lang else "en"

    @field_validator("sort_mode")
    @classmethod
    def validate_sort_mode(cls, value: str) -> str:
        mode = value.strip().lower()
        if mode not in {"date", "relevance"}:
            raise ValueError("sort_mode must be either 'date' or 'relevance'")
        return mode


class FeedCreateRequest(BaseModel):
    name: str = Field(..., min_length=3, max_length=100)
    description: Optional[str] = Field(default=None, max_length=2000)
    filters: FeedFilters = Field(default_factory=FeedFilters)
    format: str = Field(default="json")
    api_key_id: UUID

    @field_validator("name")
    @classmethod
    def validate_name(cls, value: str) -> str:
        cleaned = _sanitize_name(value, max_len=100)
        if len(cleaned) < 3:
            raise ValueError("Name must be at least 3 characters long")
        return cleaned

    @field_validator("description")
    @classmethod
    def sanitize_description(cls, value: Optional[str]) -> Optional[str]:
        if value is None:
            return None
        return _sanitize_name(value, max_len=2000) or None

    @field_validator("format")
    @classmethod
    def validate_format(cls, value: str) -> str:
        normalized = value.strip().lower()
        if normalized not in {"json", "rss", "atom"}:
            raise ValueError("format must be one of: json, rss, atom")
        return normalized


class FeedUpdateRequest(BaseModel):
    name: Optional[str] = Field(default=None, min_length=3, max_length=100)
    description: Optional[str] = Field(default=None, max_length=2000)
    filters: Optional[FeedFilters] = None
    format: Optional[str] = None
    is_active: Optional[bool] = None

    @field_validator("name")
    @classmethod
    def validate_name(cls, value: Optional[str]) -> Optional[str]:
        if value is None:
            return None
        cleaned = _sanitize_name(value, max_len=100)
        if len(cleaned) < 3:
            raise ValueError("Name must be at least 3 characters long")
        return cleaned

    @field_validator("description")
    @classmethod
    def sanitize_description(cls, value: Optional[str]) -> Optional[str]:
        if value is None:
            return None
        return _sanitize_name(value, max_len=2000) or None

    @field_validator("format")
    @classmethod
    def validate_format(cls, value: Optional[str]) -> Optional[str]:
        if value is None:
            return None
        normalized = value.strip().lower()
        if normalized not in {"json", "rss", "atom"}:
            raise ValueError("format must be one of: json, rss, atom")
        return normalized


class FeedResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    feed_id: UUID
    slug: str
    name: str
    description: Optional[str] = None
    filters: Dict[str, Any]
    default_format: str
    is_active: bool
    created_at: datetime
    updated_at: datetime
    feed_url: str
    rss_url: str
    atom_url: str


class FeedListResponse(BaseModel):
    total: int
    feeds: List[FeedResponse]


class BundleCreateRequest(BaseModel):
    name: str = Field(..., min_length=3, max_length=100)
    description: Optional[str] = Field(default=None, max_length=2000)
    feed_ids: List[UUID] = Field(..., min_length=1, max_length=20)
    format: str = Field(default="json")
    api_key_id: UUID

    @field_validator("name")
    @classmethod
    def validate_name(cls, value: str) -> str:
        cleaned = _sanitize_name(value, max_len=100)
        if len(cleaned) < 3:
            raise ValueError("Name must be at least 3 characters long")
        return cleaned

    @field_validator("description")
    @classmethod
    def sanitize_description(cls, value: Optional[str]) -> Optional[str]:
        if value is None:
            return None
        return _sanitize_name(value, max_len=2000) or None

    @field_validator("format")
    @classmethod
    def validate_format(cls, value: str) -> str:
        normalized = value.strip().lower()
        if normalized not in {"json", "rss", "atom"}:
            raise ValueError("format must be one of: json, rss, atom")
        return normalized


class BundleUpdateRequest(BaseModel):
    name: Optional[str] = Field(default=None, min_length=3, max_length=100)
    description: Optional[str] = Field(default=None, max_length=2000)
    format: Optional[str] = None
    is_active: Optional[bool] = None

    @field_validator("name")
    @classmethod
    def validate_name(cls, value: Optional[str]) -> Optional[str]:
        if value is None:
            return None
        cleaned = _sanitize_name(value, max_len=100)
        if len(cleaned) < 3:
            raise ValueError("Name must be at least 3 characters long")
        return cleaned

    @field_validator("description")
    @classmethod
    def sanitize_description(cls, value: Optional[str]) -> Optional[str]:
        if value is None:
            return None
        return _sanitize_name(value, max_len=2000) or None

    @field_validator("format")
    @classmethod
    def validate_format(cls, value: Optional[str]) -> Optional[str]:
        if value is None:
            return None
        normalized = value.strip().lower()
        if normalized not in {"json", "rss", "atom"}:
            raise ValueError("format must be one of: json, rss, atom")
        return normalized


class BundleResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    bundle_id: UUID
    slug: str
    name: str
    description: Optional[str] = None
    default_format: str
    is_active: bool
    created_at: datetime
    updated_at: datetime
    feed_ids: List[UUID]
    feed_url: str
    rss_url: str
    atom_url: str


class BundleListResponse(BaseModel):
    total: int
    bundles: List[BundleResponse]


class WebhookCreateRequest(BaseModel):
    target: str = Field(..., min_length=3, max_length=2048)
    platform: str = Field(..., min_length=3, max_length=50)
    feed_id: Optional[UUID] = None
    bundle_id: Optional[UUID] = None
    secret: Optional[str] = Field(default=None, max_length=512)
    batch_interval_minutes: int = Field(default=30, ge=5, le=1440)
    max_failures: int = Field(default=5, ge=1, le=20)

    @field_validator("platform")
    @classmethod
    def validate_platform(cls, value: str) -> str:
        platform = value.strip().lower()
        allowed = {"slack", "discord", "telegram", "email", "generic"}
        if platform not in allowed:
            raise ValueError(f"platform must be one of: {', '.join(sorted(allowed))}")
        return platform

    @field_validator("target")
    @classmethod
    def sanitize_target(cls, value: str) -> str:
        return value.strip()[:2048]

    @model_validator(mode="after")
    def validate_scope(self) -> "WebhookCreateRequest":
        if bool(self.feed_id) == bool(self.bundle_id):
            raise ValueError("Exactly one of feed_id or bundle_id must be provided")
        return self


class WebhookUpdateRequest(BaseModel):
    target: Optional[str] = Field(default=None, min_length=3, max_length=2048)
    secret: Optional[str] = Field(default=None, max_length=512)
    is_active: Optional[bool] = None
    batch_interval_minutes: Optional[int] = Field(default=None, ge=5, le=1440)
    max_failures: Optional[int] = Field(default=None, ge=1, le=20)

    @field_validator("target")
    @classmethod
    def sanitize_target(cls, value: Optional[str]) -> Optional[str]:
        if value is None:
            return None
        return value.strip()[:2048]


class WebhookResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    webhook_id: UUID
    platform: str
    target_preview: str
    feed_id: Optional[UUID] = None
    bundle_id: Optional[UUID] = None
    is_active: bool
    batch_interval_minutes: int
    last_triggered_at: Optional[datetime] = None
    failure_count: int
    max_failures: int
    created_at: datetime


class WebhookTestResponse(BaseModel):
    success: bool
    status_code: int
    message: str


class FeedItemResponse(BaseModel):
    article_id: UUID
    title: str
    url: str
    source_name: str
    author: Optional[str] = None
    excerpt: Optional[str] = None
    image_url: Optional[str] = None
    topics: List[str] = Field(default_factory=list)
    category: Optional[str] = None
    published_date: datetime
    relevance_score: Optional[float] = None


class IntegrationFeedResponse(BaseModel):
    feed_id: UUID
    name: str
    generated_at: datetime
    total: int
    items: List[FeedItemResponse]
    next_cursor: Optional[str] = None
