"""
Date Parsing Utilities
Centralized date parsing functions to eliminate code duplication
"""
from datetime import datetime, timezone
from typing import Optional, Any
import logging

logger = logging.getLogger(__name__)


def parse_iso_date(date_str: Optional[str], fallback_to_now: bool = True) -> Optional[datetime]:
    """
    Parse ISO 8601 date string (e.g., "2024-10-22T10:30:00Z")

    Args:
        date_str: ISO 8601 formatted date string
        fallback_to_now: If True, return current time on parse failure; if False, return None

    Returns:
        Parsed datetime object with timezone, or fallback value

    Examples:
        >>> parse_iso_date("2024-10-22T10:30:00Z")
        datetime(2024, 10, 22, 10, 30, tzinfo=timezone.utc)

        >>> parse_iso_date("invalid", fallback_to_now=False)
        None
    """
    if not date_str:
        return datetime.now(timezone.utc) if fallback_to_now else None

    try:
        # Handle both 'Z' suffix and '+00:00' formats
        normalized = date_str.replace('Z', '+00:00')
        parsed = datetime.fromisoformat(normalized)

        # Ensure timezone-aware
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)

        return parsed
    except (ValueError, AttributeError) as e:
        logger.debug(f"Failed to parse ISO date '{date_str}': {e}")
        return datetime.now(timezone.utc) if fallback_to_now else None


def parse_gdelt_date(date_str: Optional[str], fallback_to_now: bool = True) -> Optional[datetime]:
    """
    Parse GDELT date format (YYYYMMDDHHmmSS)

    Args:
        date_str: GDELT formatted date string (e.g., "20241022103000")
        fallback_to_now: If True, return current time on parse failure; if False, return None

    Returns:
        Parsed datetime object with UTC timezone, or fallback value

    Examples:
        >>> parse_gdelt_date("20241022103000")
        datetime(2024, 10, 22, 10, 30, tzinfo=timezone.utc)
    """
    if not date_str:
        return datetime.now(timezone.utc) if fallback_to_now else None

    try:
        parsed = datetime.strptime(date_str, '%Y%m%d%H%M%S')
        return parsed.replace(tzinfo=timezone.utc)
    except (ValueError, AttributeError) as e:
        logger.debug(f"Failed to parse GDELT date '{date_str}': {e}")
        return datetime.now(timezone.utc) if fallback_to_now else None


def parse_rss_date(entry: Any, fallback_to_now: bool = True) -> Optional[datetime]:
    """
    Parse RSS feed entry date from feedparser entry object

    Args:
        entry: Feedparser entry object
        fallback_to_now: If True, return current time on parse failure; if False, return None

    Returns:
        Parsed datetime object with UTC timezone, or fallback value

    Examples:
        >>> import feedparser
        >>> entry = feedparser.parse(rss_xml).entries[0]
        >>> parse_rss_date(entry)
        datetime(2024, 10, 22, 10, 30, tzinfo=timezone.utc)
    """
    try:
        # Try published_parsed first
        if hasattr(entry, 'published_parsed') and entry.published_parsed:
            from time import mktime
            return datetime.fromtimestamp(mktime(entry.published_parsed), tz=timezone.utc)

        # Fall back to updated_parsed
        if hasattr(entry, 'updated_parsed') and entry.updated_parsed:
            from time import mktime
            return datetime.fromtimestamp(mktime(entry.updated_parsed), tz=timezone.utc)

        # Try string parsing as last resort
        if hasattr(entry, 'published') and entry.published:
            return parse_iso_date(entry.published, fallback_to_now=fallback_to_now)

        if hasattr(entry, 'updated') and entry.updated:
            return parse_iso_date(entry.updated, fallback_to_now=fallback_to_now)

    except (ValueError, AttributeError, OverflowError) as e:
        logger.debug(f"Failed to parse RSS date from entry: {e}")

    return datetime.now(timezone.utc) if fallback_to_now else None


def parse_timestamp(timestamp: Any, fallback_to_now: bool = True) -> Optional[datetime]:
    """
    Parse Unix timestamp (int or float)

    Args:
        timestamp: Unix timestamp (seconds since epoch)
        fallback_to_now: If True, return current time on parse failure; if False, return None

    Returns:
        Parsed datetime object with UTC timezone, or fallback value
    """
    if timestamp is None:
        return datetime.now(timezone.utc) if fallback_to_now else None

    try:
        # Handle both int and float timestamps
        timestamp_float = float(timestamp)
        parsed = datetime.fromtimestamp(timestamp_float, tz=timezone.utc)
        return parsed
    except (ValueError, TypeError, OverflowError, OSError) as e:
        logger.debug(f"Failed to parse timestamp '{timestamp}': {e}")
        return datetime.now(timezone.utc) if fallback_to_now else None


def ensure_timezone_aware(dt: Optional[datetime], default_tz=timezone.utc) -> Optional[datetime]:
    """
    Ensure datetime object is timezone-aware

    Args:
        dt: Datetime object to check
        default_tz: Timezone to use if datetime is naive

    Returns:
        Timezone-aware datetime, or None if input is None
    """
    if dt is None:
        return None

    if dt.tzinfo is None:
        return dt.replace(tzinfo=default_tz)

    return dt


def parse_flexible_date(
    date_input: Any,
    formats: Optional[list] = None,
    fallback_to_now: bool = True
) -> Optional[datetime]:
    """
    Parse date from various formats - tries multiple strategies

    Args:
        date_input: String, datetime, or timestamp to parse
        formats: Optional list of strftime format strings to try
        fallback_to_now: If True, return current time on all failures

    Returns:
        Parsed datetime with timezone, or fallback value

    Examples:
        >>> parse_flexible_date("2024-10-22")
        datetime(2024, 10, 22, 0, 0, tzinfo=timezone.utc)

        >>> parse_flexible_date(1698000000)  # Unix timestamp
        datetime(2023, 10, 22, ..., tzinfo=timezone.utc)
    """
    # Already a datetime
    if isinstance(date_input, datetime):
        return ensure_timezone_aware(date_input)

    # Unix timestamp (int or float)
    if isinstance(date_input, (int, float)):
        return parse_timestamp(date_input, fallback_to_now)

    # String parsing
    if isinstance(date_input, str):
        # Try ISO format first (most common)
        result = parse_iso_date(date_input, fallback_to_now=False)
        if result:
            return result

        # Try GDELT format
        if date_input.isdigit() and len(date_input) == 14:
            result = parse_gdelt_date(date_input, fallback_to_now=False)
            if result:
                return result

        # Try custom formats if provided
        if formats:
            for fmt in formats:
                try:
                    parsed = datetime.strptime(date_input, fmt)
                    return ensure_timezone_aware(parsed)
                except ValueError:
                    continue

    # All parsing failed
    return datetime.now(timezone.utc) if fallback_to_now else None

