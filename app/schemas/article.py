from datetime import datetime
from typing import Optional, List, Dict, Any
from pydantic import BaseModel, Field, HttpUrl, field_validator, ConfigDict
from uuid import UUID
from app.core.sanitizer import ContentSanitizer


class ArticleBase(BaseModel):
    """Base article schema"""
    title: str = Field(..., min_length=1, max_length=500)
    content: str = Field(..., min_length=1, max_length=100000)
    description: Optional[str] = Field(None, max_length=1000)
    source_url: Optional[str] = None
    source_name: str = Field(..., min_length=1, max_length=255)
    author: Optional[str] = Field(None, max_length=255)
    image_url: Optional[str] = None
    topics: List[str] = Field(default_factory=list, max_length=20)
    category: Optional[str] = Field(None, max_length=100)
    tags: List[str] = Field(default_factory=list, max_length=30)

    @field_validator("title", "content", "description")
    @classmethod
    def sanitize_html(cls, v: Optional[str]) -> Optional[str]:
        """Sanitize to plain text so API never returns raw HTML tags."""
        if v is None:
            return v
        return ContentSanitizer.sanitize_text(v)

    @field_validator("topics", "tags")
    @classmethod
    def validate_lists(cls, v: List[str]) -> List[str]:
        """Validate and sanitize list items"""
        return [ContentSanitizer.sanitize_text(item, max_length=50) for item in v if item.strip()]


class ArticleResponse(ArticleBase):
    """Article response schema"""
    article_id: str
    title: str
    content: str
    description: Optional[str] = None
    source_url: Optional[str] = None  # Make optional, handle None
    source_name: str
    author: Optional[str] = None
    image_url: Optional[str] = None
    topics: List[str] = Field(default_factory=list)
    category: Optional[str] = None
    tags: List[str] = Field(default_factory=list)
    published_date: datetime  # Match DB field name
    word_count: int = 0
    reading_time_minutes: int = 0
    total_views: int = 0
    total_clicks: int = 0
    avg_time_spent: float = 0.0
    is_featured: bool = False
    created_at: datetime

    @field_validator('article_id', mode='before')
    @classmethod
    def convert_uuid(cls, v):
        """Convert UUID to string"""
        from uuid import UUID
        if isinstance(v, UUID):
            return str(v)
        return v

    @field_validator('published_date', 'created_at', mode='before')
    @classmethod
    def convert_datetime(cls, v):
        """Ensure datetime is properly formatted"""
        if isinstance(v, datetime):
            return v
        return v

    @field_validator('source_url', mode='before')
    @classmethod
    def handle_none_url(cls, v):
        """Convert None URLs to string"""
        if v is None:
            return None
        return str(v)

    @field_validator("title", "content", "description", mode='after')
    @classmethod
    def sanitize_html(cls, v: Optional[str]) -> Optional[str]:
        """Sanitize to plain text so API never returns raw HTML tags."""
        if v is None:
            return v
        return ContentSanitizer.sanitize_text(v)


    model_config = ConfigDict(from_attributes=True)


class ArticleListResponse(BaseModel):
    """Paginated article list response"""
    total: int
    page: int
    page_size: int
    articles: List[ArticleResponse]
    has_next: bool
    has_previous: bool


class ArticleDetailResponse(ArticleResponse):
    """Detailed article with summary"""
    summary: Optional[str] = None
    related_articles: List[ArticleResponse] = Field(default_factory=list, max_length=5)


class SummaryRequest(BaseModel):
    """Article summary generation request"""
    article_id: Optional[UUID] = None
    url: Optional[HttpUrl] = None
    text: Optional[str] = Field(None, min_length=100, max_length=50000)
    max_length: int = Field(150, ge=50, le=500)
    style: str = Field("balanced", pattern="^(brief|balanced|detailed)$")
    include_key_points: bool = Field(default=True)

    @field_validator("text")
    @classmethod
    def sanitize_text(cls, v: Optional[str]) -> Optional[str]:
        """Sanitize input text"""
        if v is None:
            return v
        return ContentSanitizer.sanitize_text(v)

    def model_post_init(self, __context):
        """Validate that at least one input is provided"""
        if not any([self.article_id, self.url, self.text]):
            raise ValueError("Must provide article_id, url, or text")


class SummaryResponse(BaseModel):
    """Article summary response"""
    article_id: Optional[UUID] = None
    summary: str
    key_points: Optional[List[str]] = None
    word_count: int
    original_length: int
    compression_ratio: float
    generated_at: datetime
    model_used: str


class NewsQuery(BaseModel):
    """News query parameters"""
    query: Optional[str] = Field(None, max_length=500)
    sources: Optional[List[str]] = Field(None, max_length=10)
    topics: Optional[List[str]] = Field(None, max_length=10)
    category: Optional[str] = Field(None, max_length=50)
    language: str = Field("en", min_length=2, max_length=2)
    from_date: Optional[datetime] = None
    to_date: Optional[datetime] = None
    page: int = Field(1, ge=1, le=100)
    page_size: int = Field(20, ge=1, le=100)
    sort_by: str = Field("relevance", pattern="^(relevance|date|popularity)$")

    @field_validator("query", "category")
    @classmethod
    def sanitize_strings(cls, v: Optional[str]) -> Optional[str]:
        """Sanitize query strings"""
        if v is None:
            return v
        return ContentSanitizer.sanitize_text(v, max_length=500)


class TrendingArticlesResponse(BaseModel):
    """Trending articles response"""
    trending: List[ArticleResponse]
    timeframe: str
    generated_at: datetime


class SearchResultsResponse(BaseModel):
    """Search results response"""
    query: str
    total: int
    results: List[ArticleResponse]
    suggestions: List[str] = Field(default_factory=list)
    facets: Dict[str, Any] = Field(default_factory=dict)


class PersonalizedFeedRequest(BaseModel):
    """Personalized feed request"""
    page: int = Field(1, ge=1, le=100)
    page_size: int = Field(20, ge=1, le=100)
    include_read: bool = Field(False)
    min_relevance_score: float = Field(0.0, ge=0.0, le=1.0)
    preferred_topics: Optional[List[str]] = Field(None, max_length=10)


class PersonalizedFeedResponse(BaseModel):
    """Personalized feed response"""
    articles: List[ArticleResponse]
    total: int
    page: int
    page_size: int
    user_preferences: Dict[str, float] = Field(default_factory=dict)
    relevance_scores: Dict[str, float] = Field(default_factory=dict)
