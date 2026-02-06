import re
from typing import Optional
from urllib.parse import urlparse
from bs4 import BeautifulSoup
import logging

logger = logging.getLogger(__name__)


class ContentSanitizer:
    """Sanitize and validate content from external sources"""

    # Dangerous HTML tags to remove completely
    DANGEROUS_TAGS = frozenset({
        'script', 'iframe', 'object', 'embed', 'link', 'style',
        'meta', 'base', 'form', 'input', 'button', 'textarea', 'select'
    })

    # Safe tags to keep
    ALLOWED_TAGS = frozenset({
        'p', 'br', 'strong', 'b', 'em', 'i', 'u', 's',
        'h1', 'h2', 'h3', 'h4', 'h5', 'h6',
        'ul', 'ol', 'li', 'blockquote', 'a', 'img',
        'div', 'span', 'pre', 'code', 'table', 'tr', 'td', 'th',
        'thead', 'tbody', 'article', 'section', 'header', 'footer',
        'figure', 'figcaption', 'time', 'mark', 'small', 'sub', 'sup'
    })

    # Safe attributes to keep
    ALLOWED_ATTRIBUTES = frozenset({
        'href', 'src', 'alt', 'title', 'class', 'id',
        'datetime', 'cite', 'colspan', 'rowspan'
    })

    # Event handler prefixes (dangerous)
    EVENT_HANDLER_PREFIX = 'on'

    @classmethod
    def sanitize_html(cls, html: Optional[str], max_length: int = 50000) -> str:
        if not html:
            return ""

        try:
            soup = BeautifulSoup(html, 'lxml')

            # Remove dangerous tags completely
            for tag in soup.find_all(list(cls.DANGEROUS_TAGS)):
                tag.decompose()

            # Process remaining tags
            for tag in soup.find_all():
                # Remove unknown tags but keep their text content
                if tag.name not in cls.ALLOWED_TAGS:
                    tag.unwrap()
                    continue

                # Remove dangerous attributes
                attrs_to_remove = [
                    attr for attr in tag.attrs
                    if attr.lower().startswith(cls.EVENT_HANDLER_PREFIX)
                    or attr.lower() not in cls.ALLOWED_ATTRIBUTES
                ]
                for attr in attrs_to_remove:
                    del tag[attr]

                # Sanitize href and src attributes
                if 'href' in tag.attrs:
                    tag['href'] = cls.sanitize_url(tag['href'])
                if 'src' in tag.attrs:
                    tag['src'] = cls.sanitize_url(tag['src'])

            result = str(soup)
            return result[:max_length] if len(result) > max_length else result

        except Exception as e:
            logger.warning(f"HTML sanitization failed, falling back to text extraction: {e}")
            return cls.strip_html(html)[:max_length]

    @classmethod
    def strip_html(cls, html: Optional[str]) -> str:
        """Remove all HTML tags, return plain text."""
        if not html:
            return ""
        try:
            return BeautifulSoup(html, 'html.parser').get_text(separator=' ')
        except Exception:
            return ""

    @classmethod
    def sanitize_text(cls, text: Optional[str], max_length: int = 10000) -> str:
        if not text:
            return ""

        # Strip any HTML tags
        text = cls.strip_html(text)

        # Normalize whitespace (collapse multiple spaces/newlines)
        text = re.sub(r'\s+', ' ', text).strip()

        return text[:max_length] if len(text) > max_length else text

    @classmethod
    def sanitize_url(cls, url: Optional[str], max_length: int = 2048) -> str:
        if not url:
            return ""

        url = url.strip()

        # Block dangerous URL schemes
        lower_url = url.lower()
        if lower_url.startswith(('javascript:', 'data:', 'vbscript:', 'file:')):
            return ""

        # Validate URL structure
        try:
            parsed = urlparse(url)
            # Allow http, https, and protocol-relative URLs
            if parsed.scheme and parsed.scheme not in ('http', 'https'):
                return ""
            # Must have a netloc (domain) for absolute URLs
            if parsed.scheme and not parsed.netloc:
                return ""
        except Exception:
            return ""

        return url[:max_length] if len(url) > max_length else url

    @classmethod
    def extract_plain_text(cls, content: Optional[str], max_length: int = 50000) -> str:
        if not content:
            return ""

        # Strip HTML and normalize
        text = cls.strip_html(content)
        text = re.sub(r'\s+', ' ', text).strip()

        return text[:max_length] if len(text) > max_length else text
