from __future__ import annotations

from datetime import datetime, timezone
from email.utils import format_datetime
from typing import Any, Dict, List, Optional
from uuid import UUID
import xml.etree.ElementTree as ET

from app.models.article import Article


def _safe_text(value: Optional[str], max_len: int = 4000) -> str:
    # ElementTree handles XML escaping; normalize whitespace and cap length.
    return (value or "").strip()[:max_len]


def _to_item(article: Article, score: Optional[float]) -> Dict[str, Any]:
    return {
        "article_id": article.article_id,
        "title": article.title or "",
        "url": article.url or "",
        "source_name": article.source_name or "",
        "author": article.author,
        "excerpt": article.excerpt,
        "image_url": article.image_url,
        "topics": article.topics or [],
        "category": article.category,
        "published_date": article.published_date,
        "relevance_score": score,
    }


def format_json_feed(
    *,
    feed_id: UUID,
    name: str,
    article_entries: List[Dict[str, Any]],
    generated_at: Optional[datetime] = None,
) -> Dict[str, Any]:
    now = generated_at or datetime.now(timezone.utc)
    items = [_to_item(entry["article"], entry.get("score")) for entry in article_entries]
    return {
        "feed_id": feed_id,
        "name": name,
        "generated_at": now,
        "total": len(items),
        "items": items,
        "next_cursor": None,
    }


def format_rss_feed(
    *,
    title: str,
    link: str,
    description: str,
    article_entries: List[Dict[str, Any]],
) -> str:
    rss = ET.Element("rss", attrib={"version": "2.0"})
    channel = ET.SubElement(rss, "channel")
    ET.SubElement(channel, "title").text = _safe_text(title, 300)
    ET.SubElement(channel, "link").text = _safe_text(link, 2048)
    ET.SubElement(channel, "description").text = _safe_text(description, 2000)
    ET.SubElement(channel, "lastBuildDate").text = format_datetime(datetime.now(timezone.utc))
    ET.SubElement(channel, "generator").text = "News Summarizer Integration API"

    for entry in article_entries:
        article: Article = entry["article"]
        item = ET.SubElement(channel, "item")
        ET.SubElement(item, "guid").text = str(article.article_id)
        ET.SubElement(item, "title").text = _safe_text(article.title, 500)
        ET.SubElement(item, "link").text = _safe_text(article.url, 2048)
        ET.SubElement(item, "description").text = _safe_text(article.excerpt or article.content or "", 2000)
        if article.published_date:
            ET.SubElement(item, "pubDate").text = format_datetime(article.published_date)
        if article.author:
            ET.SubElement(item, "author").text = _safe_text(article.author, 255)
        if article.category:
            ET.SubElement(item, "category").text = _safe_text(article.category, 120)
        for topic in article.topics or []:
            ET.SubElement(item, "category").text = _safe_text(topic, 120)
        if article.image_url:
            ET.SubElement(
                item,
                "enclosure",
                attrib={"url": _safe_text(article.image_url, 2048), "type": "image/jpeg"},
            )

    return ET.tostring(rss, encoding="utf-8", xml_declaration=True).decode("utf-8")


def format_atom_feed(
    *,
    title: str,
    link: str,
    article_entries: List[Dict[str, Any]],
) -> str:
    ns = "http://www.w3.org/2005/Atom"
    ET.register_namespace("", ns)
    feed = ET.Element(f"{{{ns}}}feed")
    ET.SubElement(feed, f"{{{ns}}}title").text = _safe_text(title, 300)
    ET.SubElement(feed, f"{{{ns}}}link", attrib={"href": _safe_text(link, 2048)})
    ET.SubElement(feed, f"{{{ns}}}updated").text = datetime.now(timezone.utc).isoformat()
    ET.SubElement(feed, f"{{{ns}}}id").text = _safe_text(link, 2048)

    for entry in article_entries:
        article: Article = entry["article"]
        atom_entry = ET.SubElement(feed, f"{{{ns}}}entry")
        ET.SubElement(atom_entry, f"{{{ns}}}id").text = str(article.article_id)
        ET.SubElement(atom_entry, f"{{{ns}}}title").text = _safe_text(article.title, 500)
        ET.SubElement(atom_entry, f"{{{ns}}}link", attrib={"href": _safe_text(article.url, 2048)})
        ET.SubElement(atom_entry, f"{{{ns}}}updated").text = (
            article.published_date.isoformat() if article.published_date else datetime.now(timezone.utc).isoformat()
        )
        ET.SubElement(atom_entry, f"{{{ns}}}summary").text = _safe_text(article.excerpt or article.content or "", 2000)
        if article.author:
            author = ET.SubElement(atom_entry, f"{{{ns}}}author")
            ET.SubElement(author, f"{{{ns}}}name").text = _safe_text(article.author, 255)

    return ET.tostring(feed, encoding="utf-8", xml_declaration=True).decode("utf-8")
