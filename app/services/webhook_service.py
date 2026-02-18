from __future__ import annotations

from datetime import datetime, timezone
from html import escape
import hmac
import hashlib
import ipaddress
import json
import re
import secrets
import socket
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import urlparse
from uuid import UUID

from cryptography.fernet import Fernet, InvalidToken
import httpx
from sqlalchemy import and_, select, update
from sqlalchemy.ext.asyncio import AsyncSession
import logging

from app.models.integration import UserFeedBundle, UserCustomFeed, UserWebhook, WebhookDeliveryJob
from app.services.email_service import email_service
from app.services.feed_service import feed_service
from config import settings

logger = logging.getLogger(__name__)


class WebhookService:
    TELEGRAM_BOT_TOKEN_PATTERN = re.compile(r"^\d+:[A-Za-z0-9_-]{35}$")
    TELEGRAM_CHAT_ID_PATTERN = re.compile(r"^(-?\d{1,20}|@[A-Za-z0-9_]{5,64})$")

    @staticmethod
    def _build_fernet_keys() -> List[Fernet]:
        keys: List[Fernet] = []
        current_key = settings.get_integration_encryption_key()
        keys.append(Fernet(current_key.encode("utf-8")))
        if settings.INTEGRATION_ENCRYPTION_KEY_PREVIOUS:
            keys.append(Fernet(settings.INTEGRATION_ENCRYPTION_KEY_PREVIOUS.encode("utf-8")))
        return keys

    @classmethod
    def encrypt_secret(cls, raw_value: Optional[str]) -> Optional[str]:
        if raw_value is None:
            return None
        fernet = cls._build_fernet_keys()[0]
        return fernet.encrypt(raw_value.encode("utf-8")).decode("utf-8")

    @classmethod
    def decrypt_secret(cls, encrypted_value: Optional[str]) -> Optional[str]:
        if not encrypted_value:
            return None
        for fernet in cls._build_fernet_keys():
            try:
                return fernet.decrypt(encrypted_value.encode("utf-8")).decode("utf-8")
            except InvalidToken:
                continue
        raise ValueError("Unable to decrypt integration secret with configured keys")

    @staticmethod
    def _is_private_host(host: str) -> bool:
        if host in {"localhost", "127.0.0.1", "::1"}:
            return True
        try:
            ip_obj = ipaddress.ip_address(host)
            return any(
                [
                    ip_obj.is_private,
                    ip_obj.is_loopback,
                    ip_obj.is_link_local,
                    ip_obj.is_multicast,
                    ip_obj.is_reserved,
                    ip_obj.is_unspecified,
                ]
            )
        except ValueError:
            pass

        try:
            records = socket.getaddrinfo(host, None)
            for record in records:
                ip = record[4][0]
                ip_obj = ipaddress.ip_address(ip)
                if any(
                    [
                        ip_obj.is_private,
                        ip_obj.is_loopback,
                        ip_obj.is_link_local,
                        ip_obj.is_multicast,
                        ip_obj.is_reserved,
                        ip_obj.is_unspecified,
                    ]
                ):
                    return True
        except Exception:
            # If host resolution fails, upstream caller can decide to reject.
            return True
        return False

    @classmethod
    def validate_target(cls, *, platform: str, target: str) -> None:
        platform = platform.lower()
        if platform == "email":
            if "@" not in target or len(target) > 320:
                raise ValueError("Invalid email target")
            return

        if platform == "telegram":
            candidate = target.strip()
            if not candidate or not cls.TELEGRAM_CHAT_ID_PATTERN.fullmatch(candidate):
                raise ValueError("Telegram target must be numeric chat_id or @channel username")
            return

        parsed = urlparse(target)
        if parsed.scheme != "https":
            raise ValueError("Webhook target must use HTTPS")
        if not parsed.hostname:
            raise ValueError("Webhook target hostname is required")
        if cls._is_private_host(parsed.hostname):
            raise ValueError("Webhook target resolves to a blocked/private network")

    @classmethod
    async def create_webhook(cls, *, user_id: UUID, data: Any, db: AsyncSession) -> UserWebhook:
        limits = settings.integration_limits
        max_webhooks = limits["max_webhooks_per_user"]

        webhook_count = await db.execute(
            select(UserWebhook.webhook_id).where(
                UserWebhook.user_id == user_id,
                UserWebhook.is_active.is_(True),
            )
        )
        if len(webhook_count.scalars().all()) >= max_webhooks:
            raise ValueError(f"Maximum webhooks reached ({max_webhooks})")

        cls.validate_target(platform=data.platform, target=data.target)
        if data.platform.lower() == "telegram" and not data.secret:
            raise ValueError("Telegram webhook requires bot token in secret")
        if data.platform.lower() == "telegram":
            cls.validate_telegram_bot_token(data.secret)

        if data.feed_id:
            result = await db.execute(
                select(UserCustomFeed).where(
                    UserCustomFeed.feed_id == data.feed_id,
                    UserCustomFeed.user_id == user_id,
                    UserCustomFeed.is_active.is_(True),
                )
            )
            if not result.scalar_one_or_none():
                raise ValueError("Feed not found")
        if data.bundle_id:
            result = await db.execute(
                select(UserFeedBundle).where(
                    UserFeedBundle.bundle_id == data.bundle_id,
                    UserFeedBundle.user_id == user_id,
                    UserFeedBundle.is_active.is_(True),
                )
            )
            if not result.scalar_one_or_none():
                raise ValueError("Bundle not found")

        min_interval = limits["min_batch_interval_minutes"]
        interval = max(data.batch_interval_minutes, min_interval)

        webhook = UserWebhook(
            user_id=user_id,
            feed_id=data.feed_id,
            bundle_id=data.bundle_id,
            platform=data.platform.lower(),
            target_encrypted=cls.encrypt_secret(data.target),
            secret_encrypted=cls.encrypt_secret(data.secret) if data.secret else None,
            batch_interval_minutes=interval,
            max_failures=min(data.max_failures, settings.INTEGRATION_WEBHOOK_MAX_FAILURES),
            is_active=True,
        )
        db.add(webhook)
        await db.commit()
        await db.refresh(webhook)
        return webhook

    @classmethod
    async def list_webhooks(cls, *, user_id: UUID, db: AsyncSession) -> List[UserWebhook]:
        result = await db.execute(
            select(UserWebhook).where(UserWebhook.user_id == user_id).order_by(UserWebhook.created_at.desc())
        )
        return list(result.scalars().all())

    @classmethod
    async def update_webhook(cls, *, webhook_id: UUID, user_id: UUID, data: Any, db: AsyncSession) -> Optional[UserWebhook]:
        result = await db.execute(
            select(UserWebhook).where(
                UserWebhook.webhook_id == webhook_id,
                UserWebhook.user_id == user_id,
            )
        )
        webhook = result.scalar_one_or_none()
        if not webhook:
            return None

        limits = settings.integration_limits
        if data.target is not None:
            cls.validate_target(platform=webhook.platform, target=data.target)
            webhook.target_encrypted = cls.encrypt_secret(data.target)
        if data.secret is not None:
            if webhook.platform.lower() == "telegram" and not data.secret:
                raise ValueError("Telegram webhook requires bot token in secret")
            if webhook.platform.lower() == "telegram":
                cls.validate_telegram_bot_token(data.secret)
            webhook.secret_encrypted = cls.encrypt_secret(data.secret) if data.secret else None
        if data.is_active is not None:
            webhook.is_active = data.is_active
        if data.batch_interval_minutes is not None:
            webhook.batch_interval_minutes = max(data.batch_interval_minutes, limits["min_batch_interval_minutes"])
        if data.max_failures is not None:
            webhook.max_failures = min(data.max_failures, settings.INTEGRATION_WEBHOOK_MAX_FAILURES)

        await db.commit()
        await db.refresh(webhook)
        return webhook

    @classmethod
    async def delete_webhook(cls, *, webhook_id: UUID, user_id: UUID, db: AsyncSession) -> bool:
        result = await db.execute(
            select(UserWebhook).where(
                UserWebhook.webhook_id == webhook_id,
                UserWebhook.user_id == user_id,
                UserWebhook.is_active.is_(True),
            )
        )
        webhook = result.scalar_one_or_none()
        if not webhook:
            return False

        webhook.is_active = False

        await db.execute(
            update(WebhookDeliveryJob)
            .where(
                WebhookDeliveryJob.webhook_id == webhook_id,
                WebhookDeliveryJob.status.in_(["pending", "retry_pending"]),
            )
            .values(
                status="cancelled",
                updated_at=datetime.now(timezone.utc),
            )
        )
        await db.commit()
        return True

    @staticmethod
    def get_target_preview(webhook: UserWebhook) -> str:
        try:
            target = WebhookService.decrypt_secret(webhook.target_encrypted) or ""
        except Exception:
            return "******"

        if webhook.platform == "email":
            local, _, domain = target.partition("@")
            if not domain:
                return "******"
            return f"{local[:2]}***@{domain}"

        parsed = urlparse(target)
        if parsed.netloc:
            return f"{parsed.scheme}://{parsed.netloc}/***"
        return "******"

    @staticmethod
    def _build_delivery_payload(*, source_id: str, source_name: str, items: List[Dict[str, Any]]) -> Dict[str, Any]:
        return {
            "id": f"evt_{secrets.token_hex(8)}",
            "type": "feed_update",
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "source": {
                "id": source_id,
                "name": source_name,
            },
            "data": {
                "items_new": items,
                "count": len(items),
            },
        }

    @staticmethod
    def _sign_payload(*, payload_bytes: bytes, secret: Optional[str]) -> Optional[str]:
        if not secret:
            return None
        return hmac.new(secret.encode("utf-8"), payload_bytes, hashlib.sha256).hexdigest()

    @classmethod
    def validate_telegram_bot_token(cls, token: Optional[str]) -> None:
        token_value = (token or "").strip()
        if not token_value:
            raise ValueError("Telegram webhook requires bot token in secret")
        if not cls.TELEGRAM_BOT_TOKEN_PATTERN.fullmatch(token_value):
            raise ValueError("Telegram bot token format is invalid")

    @staticmethod
    def _redacted_http_error(platform: str, status_code: int) -> str:
        return f"{platform}_http_{status_code}"

    @classmethod
    async def _post_json(
        cls,
        *,
        url: str,
        payload: Dict[str, Any],
        secret: Optional[str],
    ) -> Tuple[bool, int, str]:
        payload_bytes = json.dumps(payload, separators=(",", ":"), ensure_ascii=True).encode("utf-8")
        signature = cls._sign_payload(payload_bytes=payload_bytes, secret=secret)

        headers = {"Content-Type": "application/json"}
        if signature:
            headers["X-Webhook-Signature"] = signature
            headers["X-Webhook-Timestamp"] = str(int(datetime.now(timezone.utc).timestamp()))

        timeout = httpx.Timeout(settings.INTEGRATION_WEBHOOK_TIMEOUT_SECONDS)
        async with httpx.AsyncClient(timeout=timeout, follow_redirects=False) as client:
            response = await client.post(url, headers=headers, content=payload_bytes)
            if response.status_code >= 400:
                return False, response.status_code, cls._redacted_http_error("webhook", response.status_code)
            return True, response.status_code, "delivered"

    @classmethod
    async def deliver_webhook(
        cls,
        *,
        webhook: UserWebhook,
        source_id: UUID,
        source_name: str,
        items: List[Dict[str, Any]],
    ) -> Tuple[bool, int, str]:
        if not items:
            return True, 204, "no_items"

        target = cls.decrypt_secret(webhook.target_encrypted) or ""
        secret = cls.decrypt_secret(webhook.secret_encrypted) if webhook.secret_encrypted else None
        payload = cls._build_delivery_payload(source_id=str(source_id), source_name=source_name, items=items)

        platform = webhook.platform.lower()
        if platform == "email":
            subject = f"{source_name}: {len(items)} new articles"
            lines = [f"- {item.get('title')} ({item.get('url')})" for item in items[:20]]
            body_text = "\n".join(lines) or "No new items."
            safe_lines = [escape(line) for line in lines]
            html = "<br/>".join(safe_lines) or "No new items."
            success = await email_service.send_email(target, subject, html, body_text)
            return (success, 200 if success else 500, "email_sent" if success else "email_failed")

        if platform == "telegram":
            if not secret:
                return False, 400, "telegram requires bot token in secret"
            cls.validate_telegram_bot_token(secret)
            endpoint = f"https://api.telegram.org/bot{secret}/sendMessage"
            lines = [f"- {item.get('title')}" for item in items[:10]]
            message = f"{source_name}: {len(items)} new articles\n" + "\n".join(lines)
            timeout = httpx.Timeout(settings.INTEGRATION_WEBHOOK_TIMEOUT_SECONDS)
            async with httpx.AsyncClient(timeout=timeout, follow_redirects=False) as client:
                response = await client.post(endpoint, json={"chat_id": target, "text": message})
                if response.status_code >= 400:
                    return False, response.status_code, cls._redacted_http_error("telegram", response.status_code)
                return True, response.status_code, "telegram_sent"

        if platform == "slack":
            slack_payload = {
                "text": f"{source_name}: {len(items)} new articles",
                "blocks": [
                    {
                        "type": "section",
                        "text": {"type": "mrkdwn", "text": f"*<{item.get('url')}|{item.get('title')}>*"},
                    }
                    for item in items[:10]
                ],
            }
            return await cls._post_json(url=target, payload=slack_payload, secret=secret)

        if platform == "discord":
            lines = [f"- [{item.get('title')}]({item.get('url')})" for item in items[:10]]
            discord_payload = {"content": f"{source_name}: {len(items)} new articles\n" + "\n".join(lines)}
            return await cls._post_json(url=target, payload=discord_payload, secret=secret)

        return await cls._post_json(url=target, payload=payload, secret=secret)

    @classmethod
    async def test_webhook(cls, *, webhook: UserWebhook, user_id: UUID, db: AsyncSession) -> Tuple[bool, int, str]:
        if webhook.feed_id:
            feed = await feed_service.get_feed(feed_id=webhook.feed_id, user_id=user_id, db=db)
            if not feed:
                return False, 404, "Feed not found"
            entries = await feed_service.get_feed_articles(feed=feed, user_id=user_id, db=db, limit=3)
            source_id = feed.feed_id
            source_name = feed.name
        else:
            bundle = await feed_service.get_bundle(bundle_id=webhook.bundle_id, user_id=user_id, db=db)
            if not bundle:
                return False, 404, "Bundle not found"
            entries = await feed_service.get_bundle_articles(bundle=bundle, user_id=user_id, db=db, limit=3)
            source_id = bundle.bundle_id
            source_name = bundle.name

        test_items = []
        for entry in entries:
            article = entry["article"]
            test_items.append(
                {
                    "article_id": str(article.article_id),
                    "title": article.title,
                    "url": article.url,
                    "source_name": article.source_name,
                    "published_date": article.published_date.isoformat() if article.published_date else None,
                }
            )
        return await cls.deliver_webhook(
            webhook=webhook,
            source_id=source_id,
            source_name=source_name,
            items=test_items,
        )


webhook_service = WebhookService()
