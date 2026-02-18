from __future__ import annotations

from datetime import datetime
from typing import Literal, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response, status
from sqlalchemy.ext.asyncio import AsyncSession
import logging

from app.core.database import get_db
from app.dependencies.cache import (
    build_integration_bundle_key,
    build_integration_feed_key,
    get_cached_response,
    set_cached_response,
)
from app.dependencies.rate_limit import check_integration_rate_limit
from app.schemas.integration import IntegrationFeedResponse
from app.services.api_key_service import api_key_service
from app.services.feed_formatter import format_atom_feed, format_json_feed, format_rss_feed
from app.services.feed_service import feed_service
from config import settings

logger = logging.getLogger(__name__)

def _ensure_enabled() -> None:
    if not settings.ENABLE_INTEGRATION_API:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Integration API is disabled")


router = APIRouter(
    prefix="/integration",
    tags=["Integration API"],
    dependencies=[Depends(_ensure_enabled)],
)
SortMode = Literal["date", "relevance"]


def _extract_integration_token(request: Request, query_token: Optional[str]) -> str:
    auth_header = request.headers.get("Authorization", "")
    if auth_header.startswith("Bearer "):
        return auth_header.split(" ", 1)[1].strip()

    header_key = request.headers.get(settings.INTEGRATION_KEY_HEADER)
    if header_key:
        return header_key.strip()

    if query_token:
        return query_token.strip()

    raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Missing integration token")


async def _validate_and_throttle(*, token: str, db: AsyncSession, required_scope: str = "feed:read"):
    validated_key = await api_key_service.validate_key(plain_key=token, db=db)
    if not validated_key:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid integration token")
    normalized_scopes = {scope.strip().lower() for scope in (validated_key.scopes or []) if scope}
    if required_scope and required_scope not in normalized_scopes and "*" not in normalized_scopes:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Missing required scope: {required_scope}",
        )

    await check_integration_rate_limit(
        identifier=f"integration-key:{validated_key.api_key_id}",
        limit_per_hour=validated_key.rate_limit_per_hour,
    )
    return validated_key


def _build_links(request: Request, path: str) -> str:
    return f"{str(request.base_url).rstrip('/')}{path}"


_XML_MEDIA = {"rss": "application/rss+xml", "atom": "application/atom+xml"}


async def _serve_source(
    *,
    request: Request,
    source_type: str,
    slug: str,
    fmt: str,
    token: Optional[str],
    limit: int,
    since: Optional[datetime],
    sort: SortMode,
    db: AsyncSession,
):
    """Unified handler for feed/bundle retrieval in any format."""
    _ensure_enabled()
    integration_token = _extract_integration_token(request, token)
    validated_key = await _validate_and_throttle(token=integration_token, db=db)
    owner = str(validated_key.api_key_id)

    if source_type == "feed":
        cache_key = build_integration_feed_key(
            feed_slug=slug, owner=owner, limit=limit, since=since, sort=sort, fmt=fmt,
        )
    else:
        cache_key = build_integration_bundle_key(
            bundle_slug=slug, owner=owner, limit=limit, since=since, sort=sort, fmt=fmt,
        )

    cached = await get_cached_response(cache_key)
    if cached:
        await api_key_service.increment_usage(validated_key.api_key_id)
        if isinstance(cached, dict) and "content" in cached:
            return Response(content=cached["content"], media_type=_XML_MEDIA.get(fmt, "application/xml"))
        return cached

    if source_type == "feed":
        source = await feed_service.get_feed_by_slug(slug=slug, db=db)
        label = "Feed"
    else:
        source = await feed_service.get_bundle_by_slug(slug=slug, db=db)
        label = "Bundle"

    if not source or not source.is_active:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"{label} not found")
    if source.api_key_id != validated_key.api_key_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=f"{label} does not belong to this token")

    if source_type == "feed":
        entries = await feed_service.get_feed_articles(
            feed=source, user_id=source.user_id, db=db, limit=limit, since=since, sort=sort,
        )
    else:
        entries = await feed_service.get_bundle_articles(
            bundle=source, user_id=source.user_id, db=db, limit=limit, since=since, sort=sort,
        )

    effective = source.default_format if fmt == "default" else fmt
    path_type = "feeds" if source_type == "feed" else "bundles"
    source_id = source.feed_id if source_type == "feed" else source.bundle_id

    if effective == "rss":
        xml = format_rss_feed(
            title=source.name,
            link=_build_links(request, f"/api/v1/integration/{path_type}/{source.slug}/rss"),
            description=source.description or source.name,
            article_entries=entries,
        )
        if fmt != "default":
            await set_cached_response(cache_key, {"content": xml}, settings.INTEGRATION_FEED_CACHE_TTL)
        await api_key_service.increment_usage(validated_key.api_key_id)
        return Response(content=xml, media_type="application/rss+xml")

    if effective == "atom":
        xml = format_atom_feed(
            title=source.name,
            link=_build_links(request, f"/api/v1/integration/{path_type}/{source.slug}/atom"),
            article_entries=entries,
        )
        if fmt != "default":
            await set_cached_response(cache_key, {"content": xml}, settings.INTEGRATION_FEED_CACHE_TTL)
        await api_key_service.increment_usage(validated_key.api_key_id)
        return Response(content=xml, media_type="application/atom+xml")

    payload = format_json_feed(feed_id=source_id, name=source.name, article_entries=entries)
    await set_cached_response(cache_key, payload, settings.INTEGRATION_FEED_CACHE_TTL)
    await api_key_service.increment_usage(validated_key.api_key_id)
    return IntegrationFeedResponse.model_validate(payload)


@router.get("/feeds/{feed_slug}")
async def get_feed(
    request: Request,
    feed_slug: str,
    token: Optional[str] = Query(default=None),
    limit: int = Query(default=20, ge=1, le=100),
    since: Optional[datetime] = Query(default=None),
    sort: SortMode = Query(default="date"),
    db: AsyncSession = Depends(get_db),
):
    return await _serve_source(
        request=request, source_type="feed", slug=feed_slug, fmt="default",
        token=token, limit=limit, since=since, sort=sort, db=db,
    )


@router.get("/feeds/{feed_slug}/rss")
async def get_feed_rss(
    request: Request,
    feed_slug: str,
    token: Optional[str] = Query(default=None),
    limit: int = Query(default=20, ge=1, le=100),
    since: Optional[datetime] = Query(default=None),
    sort: SortMode = Query(default="date"),
    db: AsyncSession = Depends(get_db),
):
    return await _serve_source(
        request=request, source_type="feed", slug=feed_slug, fmt="rss",
        token=token, limit=limit, since=since, sort=sort, db=db,
    )


@router.get("/feeds/{feed_slug}/atom")
async def get_feed_atom(
    request: Request,
    feed_slug: str,
    token: Optional[str] = Query(default=None),
    limit: int = Query(default=20, ge=1, le=100),
    since: Optional[datetime] = Query(default=None),
    sort: SortMode = Query(default="date"),
    db: AsyncSession = Depends(get_db),
):
    return await _serve_source(
        request=request, source_type="feed", slug=feed_slug, fmt="atom",
        token=token, limit=limit, since=since, sort=sort, db=db,
    )


@router.get("/bundles/{bundle_slug}")
async def get_bundle(
    request: Request,
    bundle_slug: str,
    token: Optional[str] = Query(default=None),
    limit: int = Query(default=20, ge=1, le=100),
    since: Optional[datetime] = Query(default=None),
    sort: SortMode = Query(default="date"),
    db: AsyncSession = Depends(get_db),
):
    return await _serve_source(
        request=request, source_type="bundle", slug=bundle_slug, fmt="default",
        token=token, limit=limit, since=since, sort=sort, db=db,
    )


@router.get("/bundles/{bundle_slug}/rss")
async def get_bundle_rss(
    request: Request,
    bundle_slug: str,
    token: Optional[str] = Query(default=None),
    limit: int = Query(default=20, ge=1, le=100),
    since: Optional[datetime] = Query(default=None),
    sort: SortMode = Query(default="date"),
    db: AsyncSession = Depends(get_db),
):
    return await _serve_source(
        request=request, source_type="bundle", slug=bundle_slug, fmt="rss",
        token=token, limit=limit, since=since, sort=sort, db=db,
    )


@router.get("/bundles/{bundle_slug}/atom")
async def get_bundle_atom(
    request: Request,
    bundle_slug: str,
    token: Optional[str] = Query(default=None),
    limit: int = Query(default=20, ge=1, le=100),
    since: Optional[datetime] = Query(default=None),
    sort: SortMode = Query(default="date"),
    db: AsyncSession = Depends(get_db),
):
    return await _serve_source(
        request=request, source_type="bundle", slug=bundle_slug, fmt="atom",
        token=token, limit=limit, since=since, sort=sort, db=db,
    )
