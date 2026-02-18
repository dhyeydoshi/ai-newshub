from __future__ import annotations

from datetime import datetime, timezone
from typing import List
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import case, func, select
from sqlalchemy.ext.asyncio import AsyncSession
import logging

from app.api.auth import get_current_user_id
from app.core.database import get_db
from app.dependencies.rate_limit import check_integration_rate_limit
from app.models.integration import (
    UserAPIKey,
    UserCustomFeed,
    UserFeedBundle,
    UserWebhook,
    WebhookDeliveryJob,
)
from app.schemas.auth import MessageResponse
from app.schemas.integration import (
    APIKeyCreateRequest,
    APIKeyCreateResponse,
    APIKeyListResponse,
    APIKeyResponse,
    BundleCreateRequest,
    BundleListResponse,
    BundleResponse,
    BundleUpdateRequest,
    FeedCreateRequest,
    FeedListResponse,
    FeedResponse,
    FeedUpdateRequest,
    WebhookCreateRequest,
    WebhookResponse,
    WebhookTestResponse,
    WebhookUpdateRequest,
)
from app.services.api_key_service import api_key_service
from app.services.feed_service import feed_service
from app.services.webhook_service import webhook_service
from config import settings

logger = logging.getLogger(__name__)


def _ensure_enabled() -> None:
    if not settings.ENABLE_INTEGRATION_API:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Integration API is disabled")


router = APIRouter(
    prefix="/integrations",
    tags=["Integration Management"],
    dependencies=[Depends(_ensure_enabled)],
)


def _parse_user_id(user_id: str) -> UUID:
    try:
        return UUID(user_id)
    except Exception as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid user identity") from exc


def _build_entity_urls(request: Request, entity_type: str, slug: str) -> dict:
    prefix = f"{str(request.base_url).rstrip('/')}/api/v1/integration/{entity_type}/{slug}"
    return {"feed_url": prefix, "rss_url": f"{prefix}/rss", "atom_url": f"{prefix}/atom"}


def _to_feed_response(feed: UserCustomFeed, request: Request) -> FeedResponse:
    return FeedResponse(
        feed_id=feed.feed_id,
        slug=feed.slug,
        name=feed.name,
        description=feed.description,
        filters=dict(feed.filters or {}),
        default_format=feed.default_format,
        is_active=feed.is_active,
        created_at=feed.created_at,
        updated_at=feed.updated_at,
        **_build_entity_urls(request, "feeds", feed.slug),
    )


def _to_bundle_response(bundle: UserFeedBundle, request: Request, feed_ids: List[UUID]) -> BundleResponse:
    return BundleResponse(
        bundle_id=bundle.bundle_id,
        slug=bundle.slug,
        name=bundle.name,
        description=bundle.description,
        default_format=bundle.default_format,
        is_active=bundle.is_active,
        created_at=bundle.created_at,
        updated_at=bundle.updated_at,
        feed_ids=feed_ids,
        **_build_entity_urls(request, "bundles", bundle.slug),
    )


def _to_webhook_response(webhook: UserWebhook) -> WebhookResponse:
    return WebhookResponse(
        webhook_id=webhook.webhook_id,
        platform=webhook.platform,
        target_preview=webhook_service.get_target_preview(webhook),
        feed_id=webhook.feed_id,
        bundle_id=webhook.bundle_id,
        is_active=webhook.is_active,
        batch_interval_minutes=webhook.batch_interval_minutes,
        last_triggered_at=webhook.last_triggered_at,
        failure_count=webhook.failure_count,
        max_failures=webhook.max_failures,
        created_at=webhook.created_at,
    )


@router.post("/api-keys", response_model=APIKeyCreateResponse, status_code=status.HTTP_201_CREATED)
async def create_api_key(
    payload: APIKeyCreateRequest,
    user_id: str = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
):
    _ensure_enabled()
    user_uuid = _parse_user_id(user_id)
    try:
        plain_key, key = await api_key_service.create_key(
            user_id=user_uuid,
            name=payload.name,
            scopes=payload.scopes,
            expires_in_days=payload.expires_in_days,
            db=db,
        )
        return APIKeyCreateResponse(
            api_key=plain_key,
            key_id=key.api_key_id,
            prefix=key.key_prefix,
            name=key.name,
            scopes=list(key.scopes or ["feed:read"]),
            expires_at=key.expires_at,
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc


@router.get("/api-keys", response_model=APIKeyListResponse)
async def list_api_keys(
    user_id: str = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
):
    _ensure_enabled()
    keys = await api_key_service.list_keys(user_id=_parse_user_id(user_id), db=db)
    return APIKeyListResponse(total=len(keys), keys=[APIKeyResponse.model_validate(key) for key in keys])


@router.delete("/api-keys/{key_id}", response_model=MessageResponse)
async def revoke_api_key(
    key_id: UUID,
    user_id: str = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
):
    _ensure_enabled()
    revoked = await api_key_service.revoke_key(key_id=key_id, user_id=_parse_user_id(user_id), db=db)
    if not revoked:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="API key not found")
    return MessageResponse(message="API key revoked", success=True)


@router.delete("/api-keys/{key_id}/permanent", response_model=MessageResponse)
async def delete_api_key(
    key_id: UUID,
    user_id: str = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
):
    _ensure_enabled()
    deleted = await api_key_service.delete_key(key_id=key_id, user_id=_parse_user_id(user_id), db=db)
    if not deleted:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="API key not found or still active")
    return MessageResponse(message="API key permanently deleted", success=True)


@router.post("/api-keys/{key_id}/rotate", response_model=APIKeyCreateResponse)
async def rotate_api_key(
    key_id: UUID,
    user_id: str = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
):
    _ensure_enabled()
    try:
        plain_key, key = await api_key_service.rotate_key(key_id=key_id, user_id=_parse_user_id(user_id), db=db)
        return APIKeyCreateResponse(
            api_key=plain_key,
            key_id=key.api_key_id,
            prefix=key.key_prefix,
            name=key.name,
            scopes=list(key.scopes or ["feed:read"]),
            expires_at=key.expires_at,
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc


@router.post("/feeds", response_model=FeedResponse, status_code=status.HTTP_201_CREATED)
async def create_feed(
    request: Request,
    payload: FeedCreateRequest,
    user_id: str = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
):
    _ensure_enabled()
    try:
        feed = await feed_service.create_feed(user_id=_parse_user_id(user_id), data=payload, db=db)
        return _to_feed_response(feed, request)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc


@router.get("/feeds", response_model=FeedListResponse)
async def list_feeds(
    request: Request,
    user_id: str = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
):
    _ensure_enabled()
    feeds = await feed_service.list_feeds(user_id=_parse_user_id(user_id), db=db)
    response_items = []
    for feed in feeds:
        response_items.append(_to_feed_response(feed, request))
    return FeedListResponse(total=len(response_items), feeds=response_items)


@router.get("/feeds/{feed_id}", response_model=FeedResponse)
async def get_feed(
    request: Request,
    feed_id: UUID,
    user_id: str = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
):
    _ensure_enabled()
    feed = await feed_service.get_feed(feed_id=feed_id, user_id=_parse_user_id(user_id), db=db)
    if not feed:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Feed not found")
    return _to_feed_response(feed, request)


@router.put("/feeds/{feed_id}", response_model=FeedResponse)
async def update_feed(
    request: Request,
    feed_id: UUID,
    payload: FeedUpdateRequest,
    user_id: str = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
):
    _ensure_enabled()
    try:
        feed = await feed_service.update_feed(
            feed_id=feed_id,
            user_id=_parse_user_id(user_id),
            data=payload,
            db=db,
        )
        return _to_feed_response(feed, request)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc


@router.delete("/feeds/{feed_id}", response_model=MessageResponse)
async def delete_feed(
    feed_id: UUID,
    user_id: str = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
):
    _ensure_enabled()
    deleted = await feed_service.delete_feed(feed_id=feed_id, user_id=_parse_user_id(user_id), db=db)
    if not deleted:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Feed not found")
    return MessageResponse(message="Feed deactivated", success=True)


@router.post("/bundles", response_model=BundleResponse, status_code=status.HTTP_201_CREATED)
async def create_bundle(
    request: Request,
    payload: BundleCreateRequest,
    user_id: str = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
):
    _ensure_enabled()
    try:
        bundle = await feed_service.create_bundle(user_id=_parse_user_id(user_id), data=payload, db=db)
        feed_ids = await feed_service.get_bundle_feed_ids(bundle_id=bundle.bundle_id, db=db)
        return _to_bundle_response(bundle, request, feed_ids)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc


@router.get("/bundles", response_model=BundleListResponse)
async def list_bundles(
    request: Request,
    user_id: str = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
):
    _ensure_enabled()
    bundles = await feed_service.list_bundles(user_id=_parse_user_id(user_id), db=db)
    response_items = []
    for bundle in bundles:
        feed_ids = await feed_service.get_bundle_feed_ids(bundle_id=bundle.bundle_id, db=db)
        response_items.append(_to_bundle_response(bundle, request, feed_ids))
    return BundleListResponse(total=len(response_items), bundles=response_items)


@router.get("/bundles/{bundle_id}", response_model=BundleResponse)
async def get_bundle(
    request: Request,
    bundle_id: UUID,
    user_id: str = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
):
    _ensure_enabled()
    bundle = await feed_service.get_bundle(bundle_id=bundle_id, user_id=_parse_user_id(user_id), db=db)
    if not bundle:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Bundle not found")
    feed_ids = await feed_service.get_bundle_feed_ids(bundle_id=bundle.bundle_id, db=db)
    return _to_bundle_response(bundle, request, feed_ids)


@router.patch("/bundles/{bundle_id}", response_model=BundleResponse)
async def update_bundle(
    request: Request,
    bundle_id: UUID,
    payload: BundleUpdateRequest,
    user_id: str = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
):
    _ensure_enabled()
    try:
        bundle = await feed_service.update_bundle(bundle_id=bundle_id, user_id=_parse_user_id(user_id), data=payload, db=db)
        feed_ids = await feed_service.get_bundle_feed_ids(bundle_id=bundle.bundle_id, db=db)
        return _to_bundle_response(bundle, request, feed_ids)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc


@router.put("/bundles/{bundle_id}/feeds/{feed_id}", response_model=MessageResponse)
async def add_feed_to_bundle(
    bundle_id: UUID,
    feed_id: UUID,
    user_id: str = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
):
    _ensure_enabled()
    try:
        await feed_service.add_feed_to_bundle(bundle_id=bundle_id, feed_id=feed_id, user_id=_parse_user_id(user_id), db=db)
        return MessageResponse(message="Feed added to bundle", success=True)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc


@router.delete("/bundles/{bundle_id}/feeds/{feed_id}", response_model=MessageResponse)
async def remove_feed_from_bundle(
    bundle_id: UUID,
    feed_id: UUID,
    user_id: str = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
):
    _ensure_enabled()
    removed = await feed_service.remove_feed_from_bundle(
        bundle_id=bundle_id,
        feed_id=feed_id,
        user_id=_parse_user_id(user_id),
        db=db,
    )
    if not removed:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Membership not found")
    return MessageResponse(message="Feed removed from bundle", success=True)


@router.delete("/bundles/{bundle_id}", response_model=MessageResponse)
async def delete_bundle(
    bundle_id: UUID,
    user_id: str = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
):
    _ensure_enabled()
    deleted = await feed_service.delete_bundle(bundle_id=bundle_id, user_id=_parse_user_id(user_id), db=db)
    if not deleted:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Bundle not found")
    return MessageResponse(message="Bundle deactivated", success=True)


@router.post("/webhooks", response_model=WebhookResponse, status_code=status.HTTP_201_CREATED)
async def create_webhook(
    payload: WebhookCreateRequest,
    user_id: str = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
):
    _ensure_enabled()
    try:
        webhook = await webhook_service.create_webhook(user_id=_parse_user_id(user_id), data=payload, db=db)
        return _to_webhook_response(webhook)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc


@router.get("/webhooks", response_model=List[WebhookResponse])
async def list_webhooks(
    user_id: str = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
):
    _ensure_enabled()
    webhooks = await webhook_service.list_webhooks(user_id=_parse_user_id(user_id), db=db)
    return [_to_webhook_response(webhook) for webhook in webhooks]


@router.patch("/webhooks/{webhook_id}", response_model=WebhookResponse)
async def update_webhook(
    webhook_id: UUID,
    payload: WebhookUpdateRequest,
    user_id: str = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
):
    _ensure_enabled()
    try:
        webhook = await webhook_service.update_webhook(
            webhook_id=webhook_id,
            user_id=_parse_user_id(user_id),
            data=payload,
            db=db,
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    if not webhook:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Webhook not found")
    return _to_webhook_response(webhook)


@router.delete("/webhooks/{webhook_id}", response_model=MessageResponse)
async def delete_webhook(
    webhook_id: UUID,
    user_id: str = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
):
    _ensure_enabled()
    deleted = await webhook_service.delete_webhook(webhook_id=webhook_id, user_id=_parse_user_id(user_id), db=db)
    if not deleted:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Webhook not found")
    return MessageResponse(message="Webhook deactivated", success=True)


@router.post("/webhooks/{webhook_id}/test", response_model=WebhookTestResponse)
async def test_webhook(
    webhook_id: UUID,
    user_id: str = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
):
    _ensure_enabled()
    user_uuid = _parse_user_id(user_id)
    await check_integration_rate_limit(
        identifier=f"integration:webhook-test:{user_uuid}",
        limit_per_hour=settings.INTEGRATION_WEBHOOK_TEST_RATE_LIMIT_PER_HOUR,
    )

    result = await db.execute(
        select(UserWebhook).where(
            UserWebhook.webhook_id == webhook_id,
            UserWebhook.user_id == user_uuid,
        )
    )
    webhook = result.scalar_one_or_none()
    if not webhook:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Webhook not found")

    success, status_code, message = await webhook_service.test_webhook(
        webhook=webhook,
        user_id=user_uuid,
        db=db,
    )
    return WebhookTestResponse(success=success, status_code=status_code, message=message)


@router.get("/stats")
async def get_integration_stats(
    user_id: str = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
):
    _ensure_enabled()
    user_uuid = _parse_user_id(user_id)

    key_stats = await db.execute(
        select(
            func.count().label("total"),
            func.count(case((UserAPIKey.is_active.is_(True), 1))).label("active"),
        ).select_from(UserAPIKey).where(UserAPIKey.user_id == user_uuid)
    )
    k = key_stats.one()

    feed_stats = await db.execute(
        select(
            func.count().label("total"),
            func.count(case((UserCustomFeed.is_active.is_(True), 1))).label("active"),
        ).select_from(UserCustomFeed).where(UserCustomFeed.user_id == user_uuid)
    )
    f = feed_stats.one()

    bundle_stats = await db.execute(
        select(
            func.count().label("total"),
            func.count(case((UserFeedBundle.is_active.is_(True), 1))).label("active"),
        ).select_from(UserFeedBundle).where(UserFeedBundle.user_id == user_uuid)
    )
    b = bundle_stats.one()

    wh_stats = await db.execute(
        select(
            func.count().label("total"),
            func.count(case((UserWebhook.is_active.is_(True), 1))).label("active"),
        ).select_from(UserWebhook).where(UserWebhook.user_id == user_uuid)
    )
    w = wh_stats.one()

    job_stats = await db.execute(
        select(
            func.count(case((WebhookDeliveryJob.status == "delivered", 1))).label("delivered"),
            func.count(case((WebhookDeliveryJob.status.in_(["pending", "retry_pending", "processing"]), 1))).label("queued"),
            func.count(case((WebhookDeliveryJob.status.in_(["failed", "dead_letter"]), 1))).label("failed"),
        )
        .select_from(WebhookDeliveryJob)
        .join(UserWebhook, UserWebhook.webhook_id == WebhookDeliveryJob.webhook_id)
        .where(UserWebhook.user_id == user_uuid)
    )
    j = job_stats.one()

    return {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "total_api_keys": k.total,
        "active_api_keys": k.active,
        "total_feeds": f.total,
        "active_feeds": f.active,
        "total_bundles": b.total,
        "active_bundles": b.active,
        "total_webhooks": w.total,
        "active_webhooks": w.active,
        "delivery_jobs": {
            "delivered": j.delivered,
            "queued": j.queued,
            "failed_or_dead_letter": j.failed,
        },
        "limits": settings.integration_limits,
    }
