import asyncio
import logging
import smtplib
import time
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from html import escape
from pathlib import Path
from typing import Any, Dict, List, Optional
from urllib.parse import quote

import httpx
from config import settings

logger = logging.getLogger(__name__)


class EmailService:
    """Email service for sending authentication emails"""

    def __init__(self):
        self.email_provider = settings.EMAIL_DELIVERY_PROVIDER
        self.email_timeout_seconds = settings.EMAIL_REQUEST_TIMEOUT_SECONDS
        self.email_max_retries = settings.EMAIL_MAX_RETRIES

        self.smtp_host = settings.SMTP_HOST
        self.smtp_port = settings.SMTP_PORT
        self.smtp_user = settings.SMTP_USER
        self.smtp_password = settings.SMTP_PASSWORD
        self.from_email = settings.SMTP_FROM_EMAIL or settings.SMTP_USER
        self.from_name = settings.SMTP_FROM_NAME

        self.graph_tenant_id = settings.GRAPH_TENANT_ID
        self.graph_client_id = settings.GRAPH_CLIENT_ID
        self.graph_client_secret = settings.GRAPH_CLIENT_SECRET
        self.graph_sender_user = settings.GRAPH_SENDER_USER or self.from_email
        self.graph_scope = settings.GRAPH_SCOPE
        self.graph_api_base_url = settings.GRAPH_API_BASE_URL.rstrip("/")
        self.graph_auth_base_url = settings.GRAPH_AUTH_BASE_URL.rstrip("/")
        self.graph_save_to_sent_items = settings.GRAPH_SAVE_TO_SENT_ITEMS
        self.graph_msa_client_id = settings.GRAPH_MSA_CLIENT_ID or settings.GRAPH_CLIENT_ID
        self.graph_msa_authority = settings.GRAPH_MSA_AUTHORITY.rstrip("/")
        self.graph_msa_scopes = settings.GRAPH_MSA_SCOPES
        self.graph_msa_token_cache_file = settings.GRAPH_MSA_TOKEN_CACHE_FILE
        self.graph_msa_auto_device_flow = settings.GRAPH_MSA_AUTO_DEVICE_FLOW

        self.frontend_url = settings.FRONTEND_URL
        self._graph_access_token: Optional[str] = None
        self._graph_access_token_expires_at: float = 0
        self._graph_token_lock = asyncio.Lock()
        self._graph_msa_lock = asyncio.Lock()
        self._graph_msa_app: Optional[Any] = None
        self._graph_msa_token_cache: Optional[Any] = None
        self._graph_msa_sdk_client: Optional[Any] = None

    @property
    def graph_token_url(self) -> str:
        return f"{self.graph_auth_base_url}/{self.graph_tenant_id}/oauth2/v2.0/token"

    def is_smtp_configured(self) -> bool:
        """Return True when minimum SMTP sender settings are available."""
        return bool(self.smtp_host and self.smtp_port and self.from_email)

    def is_graph_configured(self) -> bool:
        """Return True when Graph OAuth2 settings are available."""
        return bool(
            self.graph_tenant_id
            and self.graph_client_id
            and self.graph_client_secret
            and self.graph_sender_user
        )

    def is_graph_msa_configured(self) -> bool:
        """Return True when delegated Graph personal-mailbox settings are available."""
        return bool(self.graph_msa_client_id and self.graph_msa_scopes)

    def is_configured(self) -> bool:
        """Return True when the selected email provider has required settings."""
        if self.email_provider == "graph":
            return self.is_graph_configured()
        if self.email_provider == "graph_msa":
            return self.is_graph_msa_configured()
        if self.email_provider == "smtp":
            return self.is_smtp_configured()
        return False

    async def _get_graph_access_token(self) -> Optional[str]:
        now = time.time()
        if self._graph_access_token and now < self._graph_access_token_expires_at:
            return self._graph_access_token

        async with self._graph_token_lock:
            now = time.time()
            if self._graph_access_token and now < self._graph_access_token_expires_at:
                return self._graph_access_token

            token_payload = {
                "client_id": self.graph_client_id,
                "client_secret": self.graph_client_secret,
                "scope": self.graph_scope,
                "grant_type": "client_credentials",
            }

            try:
                async with httpx.AsyncClient(timeout=self.email_timeout_seconds) as client:
                    response = await client.post(self.graph_token_url, data=token_payload)
            except Exception as exc:
                logger.error("Graph token request failed: %s", exc)
                return None

            if response.status_code != 200:
                logger.error(
                    "Graph token request failed with status %s: %s",
                    response.status_code,
                    response.text[:500],
                )
                return None

            payload = response.json()
            access_token = payload.get("access_token")
            expires_in = int(payload.get("expires_in", 3600))
            if not access_token:
                logger.error("Graph token response did not include access_token")
                return None

            self._graph_access_token = access_token
            self._graph_access_token_expires_at = time.time() + max(expires_in - 60, 60)
            return self._graph_access_token

    @staticmethod
    def _parse_retry_after_seconds(header_value: Optional[str], default_seconds: int = 2) -> int:
        if not header_value:
            return default_seconds
        try:
            parsed = int(float(header_value))
            return max(parsed, 1)
        except (ValueError, TypeError):
            return default_seconds

    async def _send_email_via_graph(
        self,
        to_email: str,
        subject: str,
        html_content: str,
        text_content: Optional[str] = None,
    ) -> bool:
        if not self.is_graph_configured():
            logger.error("Graph email settings are incomplete; cannot send email")
            return False

        max_attempts = max(self.email_max_retries, 1)
        encoded_sender = quote(str(self.graph_sender_user), safe="")
        send_mail_url = f"{self.graph_api_base_url}/users/{encoded_sender}/sendMail"

        body_type = "HTML" if html_content else "Text"
        body_content = html_content if html_content else (text_content or "")
        payload = {
            "message": {
                "subject": subject,
                "body": {
                    "contentType": body_type,
                    "content": body_content,
                },
                "from": {
                    "emailAddress": {
                        "address": self.from_email,
                        "name": self.from_name,
                    }
                },
                "toRecipients": [
                    {"emailAddress": {"address": to_email}},
                ],
            },
            "saveToSentItems": self.graph_save_to_sent_items,
        }

        for attempt in range(1, max_attempts + 1):
            access_token = await self._get_graph_access_token()
            if not access_token:
                return False

            headers = {
                "Authorization": f"Bearer {access_token}",
                "Content-Type": "application/json",
            }

            try:
                async with httpx.AsyncClient(timeout=self.email_timeout_seconds) as client:
                    response = await client.post(send_mail_url, headers=headers, json=payload)
            except Exception as exc:
                logger.error("Graph sendMail request failed (attempt %s/%s): %s", attempt, max_attempts, exc)
                continue

            if response.status_code == 202:
                logger.info("Email sent successfully to %s via Microsoft Graph", to_email)
                return True

            if response.status_code == 401 and attempt < max_attempts:
                self._graph_access_token = None
                self._graph_access_token_expires_at = 0
                continue

            if response.status_code in (429, 503) and attempt < max_attempts:
                retry_seconds = self._parse_retry_after_seconds(response.headers.get("Retry-After"))
                await asyncio.sleep(retry_seconds)
                continue

            logger.error(
                "Graph sendMail failed with status %s for %s: %s",
                response.status_code,
                to_email,
                response.text[:500],
            )
            return False

        return False

    def _resolve_graph_msa_scopes(self, requested_scopes: Optional[List[str]] = None) -> List[str]:
        scopes = requested_scopes if requested_scopes else self.graph_msa_scopes
        reserved_scopes = {"offline_access", "openid", "profile"}
        normalized = [str(scope).strip() for scope in scopes if str(scope).strip()]
        filtered = [scope for scope in normalized if scope.lower() not in reserved_scopes]
        return filtered or ["https://graph.microsoft.com/Mail.Send"]

    def _load_graph_msa_token_cache_sync(self) -> Any:
        import msal

        cache = msal.SerializableTokenCache()
        cache_path = Path(self.graph_msa_token_cache_file)
        if cache_path.exists():
            try:
                cache.deserialize(cache_path.read_text(encoding="utf-8"))
            except Exception as exc:
                logger.warning("Failed to load MSAL token cache file %s: %s", cache_path, exc)
        return cache

    def _persist_graph_msa_token_cache_sync(self) -> None:
        if not self._graph_msa_token_cache:
            return

        changed = bool(getattr(self._graph_msa_token_cache, "has_state_changed", False))
        if not changed:
            return

        cache_path = Path(self.graph_msa_token_cache_file)
        try:
            cache_path.parent.mkdir(parents=True, exist_ok=True)
            cache_path.write_text(self._graph_msa_token_cache.serialize(), encoding="utf-8")
        except Exception as exc:
            logger.error("Failed to persist MSAL token cache to %s: %s", cache_path, exc)

    def _ensure_graph_msa_app_sync(self) -> Any:
        if self._graph_msa_app:
            return self._graph_msa_app

        if not self.graph_msa_client_id:
            raise RuntimeError("GRAPH_MSA_CLIENT_ID is required for graph_msa provider")

        import msal

        self._graph_msa_token_cache = self._load_graph_msa_token_cache_sync()
        self._graph_msa_app = msal.PublicClientApplication(
            client_id=self.graph_msa_client_id,
            authority=self.graph_msa_authority,
            token_cache=self._graph_msa_token_cache,
        )
        return self._graph_msa_app

    def _acquire_graph_msa_token_sync(
        self,
        requested_scopes: Optional[List[str]] = None,
    ) -> Optional[Dict[str, Any]]:
        scopes = self._resolve_graph_msa_scopes(requested_scopes)
        app = self._ensure_graph_msa_app_sync()

        accounts = app.get_accounts()
        if accounts:
            result = app.acquire_token_silent(scopes, account=accounts[0])
            if result and result.get("access_token"):
                self._persist_graph_msa_token_cache_sync()
                return result

        if not self.graph_msa_auto_device_flow:
            logger.error(
                "No delegated token available for graph_msa. Run scripts/bootstrap_graph_msa_token.py to initialize token cache."
            )
            return None

        flow = app.initiate_device_flow(scopes=scopes)
        user_message = flow.get("message")
        if not flow.get("user_code") or not user_message:
            logger.error("Unable to start MSAL device flow: %s", flow)
            return None

        logger.warning("Complete Microsoft device-code authentication to enable email sending:\n%s", user_message)
        result = app.acquire_token_by_device_flow(flow)
        if result and result.get("access_token"):
            self._persist_graph_msa_token_cache_sync()
            return result

        logger.error("MSAL device flow failed: %s", result)
        return None

    async def _get_graph_msa_token(
        self,
        requested_scopes: Optional[List[str]] = None,
    ) -> Optional[Dict[str, Any]]:
        async with self._graph_msa_lock:
            return await asyncio.to_thread(self._acquire_graph_msa_token_sync, requested_scopes)

    async def _ensure_graph_msa_sdk_client(self) -> Optional[Any]:
        if self._graph_msa_sdk_client:
            return self._graph_msa_sdk_client

        try:
            from azure.core.credentials import AccessToken
            from azure.core.credentials_async import AsyncTokenCredential
            from azure.core.exceptions import ClientAuthenticationError
            from msgraph import GraphServiceClient
        except Exception as exc:
            logger.error(
                "graph_msa provider requires msal + msgraph-sdk dependencies. Import error: %s",
                exc,
            )
            return None

        service = self

        class MsalAsyncTokenCredential(AsyncTokenCredential):
            async def get_token(self, *scopes: str, **kwargs) -> AccessToken:
                requested_scopes = [scope for scope in scopes if scope]
                token_result = await service._get_graph_msa_token(requested_scopes)
                if not token_result or not token_result.get("access_token"):
                    raise ClientAuthenticationError(
                        message="Unable to acquire delegated Graph token via MSAL token cache."
                    )

                expires_on_raw = token_result.get("expires_on")
                try:
                    expires_on = int(float(expires_on_raw))
                except (TypeError, ValueError):
                    expires_on = int(time.time()) + 300

                return AccessToken(token_result["access_token"], expires_on)

            async def close(self) -> None:
                return None

        self._graph_msa_sdk_client = GraphServiceClient(
            credentials=MsalAsyncTokenCredential(),
            scopes=self._resolve_graph_msa_scopes(),
        )
        return self._graph_msa_sdk_client

    @staticmethod
    def _extract_exception_status_code(exc: Exception) -> Optional[int]:
        for attr_name in ("response_status_code", "status_code", "code"):
            value = getattr(exc, attr_name, None)
            if isinstance(value, int):
                return value

        response = getattr(exc, "response", None)
        status_code = getattr(response, "status_code", None)
        if isinstance(status_code, int):
            return status_code

        return None

    def _resolve_graph_msa_send_mail_action(self, graph_client: Any) -> tuple[Any, str]:
        """
        Resolve sendMail request builder for delegated Graph flow.

        Preference order:
        1) /users/{GRAPH_SENDER_USER}/sendMail when GRAPH_SENDER_USER is set
        2) /me/sendMail fallback
        """
        sender = (self.graph_sender_user or "").strip()
        if sender:
            users_builder = getattr(graph_client, "users", None)
            by_user_id = getattr(users_builder, "by_user_id", None) if users_builder else None
            if callable(by_user_id):
                try:
                    return by_user_id(sender).send_mail, f"users/{sender}"
                except Exception as exc:
                    logger.warning(
                        "Unable to build users/%s/sendMail request in graph_msa mode; falling back to me/sendMail: %s",
                        sender,
                        exc,
                    )

        return graph_client.me.send_mail, "me"

    async def _send_email_via_graph_msa_sdk(
        self,
        to_email: str,
        subject: str,
        html_content: str,
        text_content: Optional[str] = None,
    ) -> bool:
        if not self.is_graph_msa_configured():
            logger.error("Graph MSA settings are incomplete; cannot send email")
            return False

        graph_client = await self._ensure_graph_msa_sdk_client()
        if not graph_client:
            return False

        try:
            from msgraph.generated.models.body_type import BodyType
            from msgraph.generated.models.email_address import EmailAddress
            from msgraph.generated.models.item_body import ItemBody
            from msgraph.generated.models.message import Message
            from msgraph.generated.models.recipient import Recipient
            from msgraph.generated.users.item.send_mail.send_mail_post_request_body import (
                SendMailPostRequestBody,
            )
        except Exception as exc:
            logger.error("Failed to import Graph SDK mail models: %s", exc)
            return False

        body_value = html_content if html_content else (text_content or "")
        body_type = BodyType.Html if html_content else BodyType.Text

        message = Message()
        message.subject = subject

        message.body = ItemBody()
        message.body.content_type = body_type
        message.body.content = body_value

        from_recipient = Recipient()
        from_recipient.email_address = EmailAddress()
        from_recipient.email_address.address = self.from_email
        from_recipient.email_address.name = self.from_name
        message.from_ = from_recipient

        to_recipient = Recipient()
        to_recipient.email_address = EmailAddress()
        to_recipient.email_address.address = to_email
        message.to_recipients = [to_recipient]

        request_body = SendMailPostRequestBody()
        request_body.message = message
        request_body.save_to_sent_items = self.graph_save_to_sent_items

        send_mail_action, send_path = self._resolve_graph_msa_send_mail_action(graph_client)
        max_attempts = max(self.email_max_retries, 1)
        for attempt in range(1, max_attempts + 1):
            try:
                await send_mail_action.post(body=request_body)
                logger.info(
                    "Email sent successfully to %s via Microsoft Graph SDK (delegated, path=%s)",
                    to_email,
                    send_path,
                )
                return True
            except Exception as exc:
                status_code = self._extract_exception_status_code(exc)
                if status_code in (429, 503) and attempt < max_attempts:
                    await asyncio.sleep(2)
                    continue
                if status_code in (403, 404) and send_path != "me" and attempt < max_attempts:
                    logger.warning(
                        "graph_msa sender path %s failed with status %s; retrying with me/sendMail",
                        send_path,
                        status_code,
                    )
                    send_mail_action = graph_client.me.send_mail
                    send_path = "me"
                    continue
                if status_code == 401 and attempt < max_attempts:
                    self._graph_msa_sdk_client = None
                    graph_client = await self._ensure_graph_msa_sdk_client()
                    if not graph_client:
                        return False
                    send_mail_action, send_path = self._resolve_graph_msa_send_mail_action(graph_client)
                    continue

                logger.error(
                    "Graph SDK delegated sendMail failed for %s (status=%s, path=%s): %s",
                    to_email,
                    status_code,
                    send_path,
                    exc,
                )
                return False

        return False

    def _send_smtp_sync(self, msg: MIMEMultipart) -> None:
        """Synchronous SMTP delivery — executed via asyncio.to_thread."""
        with smtplib.SMTP(self.smtp_host, self.smtp_port) as server:
            server.starttls()
            if self.smtp_user and self.smtp_password:
                server.login(self.smtp_user, self.smtp_password)
            server.send_message(msg)

    async def _send_email_via_smtp(
        self,
        to_email: str,
        subject: str,
        html_content: str,
        text_content: Optional[str] = None,
    ) -> bool:
        if not self.is_smtp_configured():
            logger.error("SMTP email settings are incomplete; cannot send email")
            return False

        try:
            msg = MIMEMultipart("alternative")
            msg["Subject"] = subject
            msg["From"] = f"{self.from_name} <{self.from_email}>"
            msg["To"] = to_email

            if text_content:
                msg.attach(MIMEText(text_content, "plain"))

            msg.attach(MIMEText(html_content, "html"))

            await asyncio.to_thread(self._send_smtp_sync, msg)

            logger.info("Email sent successfully to %s via SMTP", to_email)
            return True
        except Exception as exc:
            logger.error("SMTP send failed for %s: %s", to_email, exc)
            return False

    async def send_email(
        self,
        to_email: str,
        subject: str,
        html_content: str,
        text_content: Optional[str] = None,
    ) -> bool:
        if self.email_provider == "graph":
            return await self._send_email_via_graph(to_email, subject, html_content, text_content)

        if self.email_provider == "graph_msa":
            return await self._send_email_via_graph_msa_sdk(to_email, subject, html_content, text_content)

        if self.email_provider == "smtp":
            return await self._send_email_via_smtp(to_email, subject, html_content, text_content)

        logger.error(
            "Unsupported EMAIL_DELIVERY_PROVIDER=%s. Use 'smtp', 'graph', or 'graph_msa'.",
            self.email_provider,
        )
        return False

    @staticmethod
    def _email_layout(body_html: str) -> str:
        """Shared HTML email wrapper with common styles and copyright footer."""
        app_name = escape(settings.APP_NAME)
        return f"""
        <!DOCTYPE html>
        <html>
        <head>
            <style>
                body {{ font-family: Arial, sans-serif; line-height: 1.6; color: #333; }}
                .container {{ max-width: 600px; margin: 0 auto; padding: 20px; }}
                .btn {{ display: inline-block; padding: 12px 24px; color: white; text-decoration: none; border-radius: 4px; margin: 20px 0; }}
                .footer {{ margin-top: 30px; font-size: 12px; color: #666; }}
            </style>
        </head>
        <body>
            <div class="container">
                {body_html}
                <div class="footer">
                    <p>&copy; {app_name}. All rights reserved.</p>
                </div>
            </div>
        </body>
        </html>
        """

    async def send_verification_email(
        self,
        to_email: str,
        username: str,
        verification_token: str,
    ) -> bool:
        """Send email verification link"""
        link = f"{self.frontend_url.rstrip('/')}/?verify_token={verification_token}"
        safe_user = escape(username)
        safe_link = escape(link, quote=True)
        safe_app = escape(settings.APP_NAME)

        html_content = self._email_layout(f"""
                <h2>Welcome to {safe_app}!</h2>
                <p>Hello {safe_user},</p>
                <p>Thank you for registering. Please verify your email address by clicking the button below:</p>
                <a href="{safe_link}" class="btn" style="background-color: #4CAF50;">Verify Email Address</a>
                <p>Or copy and paste this link into your browser:</p>
                <p style="word-break: break-all;">{safe_link}</p>
                <p>This link will expire in 24 hours.</p>
                <p>If you didn't create an account, please ignore this email.</p>""")

        text_content = f"""
        Welcome to {settings.APP_NAME}!

        Hello {username},

        Thank you for registering. Please verify your email address by visiting:
        {link}

        This link will expire in 24 hours.

        If you didn't create an account, please ignore this email.
        """

        return await self.send_email(
            to_email, f"Verify your {settings.APP_NAME} account", html_content, text_content
        )

    async def send_password_reset_email(
        self,
        to_email: str,
        username: str,
        reset_token: str,
    ) -> bool:
        """Send password reset link"""
        link = f"{self.frontend_url.rstrip('/')}/?reset_token={reset_token}"
        safe_user = escape(username)
        safe_link = escape(link, quote=True)

        html_content = self._email_layout(f"""
                <h2>Password Reset Request</h2>
                <p>Hello {safe_user},</p>
                <p>We received a request to reset your password. Click the button below to proceed:</p>
                <a href="{safe_link}" class="btn" style="background-color: #f44336;">Reset Password</a>
                <p>Or copy and paste this link into your browser:</p>
                <p style="word-break: break-all;">{safe_link}</p>
                <div style="background-color: #fff3cd; padding: 15px; border-radius: 4px; margin: 20px 0;">
                    <strong>Security Notice:</strong>
                    <p>This link will expire in 1 hour for security reasons.</p>
                    <p>If you didn't request a password reset, please ignore this email and your password will remain unchanged.</p>
                </div>""")

        text_content = f"""
        Password Reset Request

        Hello {username},

        We received a request to reset your password. Visit this link to proceed:
        {link}

        This link will expire in 1 hour.

        If you didn't request a password reset, please ignore this email.
        """

        return await self.send_email(
            to_email, f"Reset your {settings.APP_NAME} password", html_content, text_content
        )

    async def send_account_locked_email(
        self,
        to_email: str,
        username: str,
        locked_until: str,
    ) -> bool:
        """Send account locked notification"""
        safe_user = escape(username)
        safe_time = escape(locked_until)

        html_content = self._email_layout(f"""
                <div style="background-color: #f44336; color: white; padding: 15px; border-radius: 4px; margin: 20px 0;">
                    <h2>Account Temporarily Locked</h2>
                </div>
                <p>Hello {safe_user},</p>
                <p>Your account has been temporarily locked due to multiple failed login attempts.</p>
                <p><strong>Account will be unlocked at:</strong> {safe_time}</p>
                <p>If this wasn't you, please contact support immediately.</p>""")

        text_content = f"""
        Security Alert: Account Temporarily Locked

        Hello {username},

        Your account has been temporarily locked due to multiple failed login attempts.

        Account will be unlocked at: {locked_until}

        If this wasn't you, please contact support immediately.
        """

        return await self.send_email(
            to_email, f"Security Alert: {settings.APP_NAME} account locked", html_content, text_content
        )


# Global email service instance
email_service = EmailService()
