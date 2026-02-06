from datetime import datetime, timezone
from typing import Optional, List, Dict, Any
from pydantic import BaseModel, Field, field_validator, model_validator, ConfigDict
import hashlib
import re
import logging

from app.core.sanitizer import ContentSanitizer

logger = logging.getLogger(__name__)


class RawArticle(BaseModel):
    
    model_config = ConfigDict(
        str_strip_whitespace=True,
        validate_assignment=True,
        extra='ignore'  # Ignore unknown fields from source APIs
    )

    # === Required fields ===
    title: str = Field(..., min_length=1, max_length=2000)
    url: str = Field(..., min_length=1, max_length=2048)
    source: str = Field(..., min_length=1, max_length=255)
    published_date: datetime

    # === Content fields ===
    content: str = Field(default="", max_length=50000)
    description: Optional[str] = Field(default=None, max_length=1000)

    # === Metadata ===
    author: Optional[str] = Field(default=None, max_length=255)
    image_url: Optional[str] = Field(default=None, max_length=2048)
    source_url: Optional[str] = Field(default=None, max_length=2048)
    category: Optional[str] = Field(default=None, max_length=100)
    language: str = Field(default="en", max_length=10)

    # === Categorization ===
    topics: List[str] = Field(default_factory=list)
    tags: List[str] = Field(default_factory=list)

    # === Extra metadata (source-specific data) ===
    metadata: Dict[str, Any] = Field(default_factory=dict)

    # === Computed fields (set by validators) ===
    content_hash: Optional[str] = Field(default=None)
    word_count: int = Field(default=0)
    reading_time_minutes: int = Field(default=1)


    @field_validator('title', mode='before')
    @classmethod
    def clean_title(cls, v: Any) -> str:
        """Sanitize title: strip HTML, normalize whitespace."""
        if v is None:
            return ""
        return ContentSanitizer.sanitize_text(str(v), max_length=2000)

    @field_validator('url', 'image_url', 'source_url', mode='before')
    @classmethod
    def clean_url(cls, v: Any) -> str:
        """Validate and sanitize URLs."""
        if v is None:
            return ""
        return ContentSanitizer.sanitize_url(str(v))

    @field_validator('content', mode='before')
    @classmethod
    def clean_content(cls, v: Any) -> str:
        """Normalize content to plain text for consistent storage and serving."""
        if v is None:
            return ""
        return ContentSanitizer.sanitize_text(str(v), max_length=50000)

    @field_validator('description', mode='before')
    @classmethod
    def clean_description(cls, v: Any) -> Optional[str]:
        """Sanitize description: strip HTML, normalize whitespace."""
        if v is None:
            return None
        cleaned = ContentSanitizer.sanitize_text(str(v), max_length=1000)
        return cleaned if cleaned else None

    @field_validator('author', 'source', 'category', mode='before')
    @classmethod
    def clean_text_field(cls, v: Any) -> Optional[str]:
        """Clean simple text fields."""
        if v is None:
            return None
        cleaned = ContentSanitizer.sanitize_text(str(v), max_length=255)
        return cleaned if cleaned else None

    @field_validator('published_date', mode='before')
    @classmethod
    def ensure_datetime(cls, v: Any) -> datetime:
        """Ensure published_date is a timezone-aware datetime."""
        if v is None:
            return datetime.now(timezone.utc)
        
        if isinstance(v, datetime):
            # Ensure timezone-aware
            if v.tzinfo is None:
                return v.replace(tzinfo=timezone.utc)
            return v
        
        if isinstance(v, str):
            # Try ISO format parsing
            try:
                dt = datetime.fromisoformat(v.replace('Z', '+00:00'))
                if dt.tzinfo is None:
                    dt = dt.replace(tzinfo=timezone.utc)
                return dt
            except (ValueError, AttributeError):
                pass
        
        # Fallback to now
        logger.debug(f"Could not parse date '{v}', using current time")
        return datetime.now(timezone.utc)

    @field_validator('topics', 'tags', mode='before')
    @classmethod
    def normalize_list(cls, v: Any) -> List[str]:
        """Normalize topics/tags to list of strings."""
        if v is None:
            return []
        
        if isinstance(v, str):
            # Split comma-separated string
            items = [s.strip() for s in v.split(',') if s.strip()]
            return items[:50]  # Limit to 50 items
        
        if isinstance(v, list):
            # Clean each item
            cleaned = []
            for item in v[:50]:
                if isinstance(item, str):
                    clean_item = item.strip()[:100]
                    if clean_item:
                        cleaned.append(clean_item)
            return cleaned
        
        return []

    @field_validator('language', mode='before')
    @classmethod
    def normalize_language(cls, v: Any) -> str:
        """Normalize language code."""
        if v is None:
            return "en"
        lang = str(v).strip().lower()[:10]
        return lang if lang else "en"

    @model_validator(mode='after')
    def compute_derived_fields(self) -> 'RawArticle':
        """Compute content hash, word count, and reading time after all fields are set."""
        # Use content or description for text analysis
        text_content = self.content or self.description or ""
        plain_text = ContentSanitizer.extract_plain_text(text_content)

        # Word count
        if plain_text:
            # Avoid validate_assignment recursion inside model validators.
            object.__setattr__(self, 'word_count', len(plain_text.split()))
            # Reading time: average 200 words per minute, minimum 1 minute
            object.__setattr__(self, 'reading_time_minutes', max(1, self.word_count // 200))
        else:
            object.__setattr__(self, 'word_count', 0)
            object.__setattr__(self, 'reading_time_minutes', 1)

        # Content hash for deduplication
        hash_input = plain_text.lower() if plain_text else self.title.lower()
        normalized = re.sub(r'\s+', ' ', hash_input).strip()
        object.__setattr__(self, 'content_hash', hashlib.sha256(normalized.encode()).hexdigest())

        return self


    def to_persistence_dict(self) -> Dict[str, Any]:
        return {
            'title': self.title,
            'content': self.content,
            'description': self.description,
            'url': self.url,
            'source': self.source,
            'source_url': self.source_url,
            'author': self.author,
            'published_date': self.published_date,
            'image_url': self.image_url,
            'category': self.category,
            'language': self.language,
            'topics': self.topics,
            'tags': self.tags,
            'metadata': self.metadata,
            'content_hash': self.content_hash,
            'word_count': self.word_count,
            'reading_time_minutes': self.reading_time_minutes,
        }

    def to_cache_dict(self) -> Dict[str, Any]:
        data = self.to_persistence_dict()
        data['published_date'] = self.published_date.isoformat()
        return data

    @classmethod
    def from_cache_dict(cls, data: Dict[str, Any]) -> 'RawArticle':
        """Reconstruct from cached dictionary."""
        return cls.model_validate(data)
