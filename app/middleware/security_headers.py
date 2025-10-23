"""
Security Headers Middleware
Implements comprehensive security headers for API protection
"""
from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import Response
from config import settings
import logging

logger = logging.getLogger(__name__)


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """
    Adds security headers to all responses
    Implements OWASP best practices
    """

    async def dispatch(self, request: Request, call_next) -> Response:
        """Add security headers to response"""

        response: Response = await call_next(request)

        # Remove server header (don't expose server info)
        if "Server" in response.headers:
            del response.headers["Server"]

        # Basic security headers (always applied)
        security_headers = {
            # Prevent MIME type sniffing
            "X-Content-Type-Options": "nosniff",

            # Prevent clickjacking
            "X-Frame-Options": "DENY",

            # XSS Protection (legacy but still useful)
            "X-XSS-Protection": "1; mode=block",

            # Referrer policy
            "Referrer-Policy": "strict-origin-when-cross-origin",

            # Permissions policy (disable dangerous features)
            "Permissions-Policy": (
                "geolocation=(), "
                "microphone=(), "
                "camera=(), "
                "payment=(), "
                "usb=(), "
                "magnetometer=(), "
                "gyroscope=(), "
                "accelerometer=()"
            ),

            # Don't cache sensitive data
            "Cache-Control": "no-store, no-cache, must-revalidate, private",
            "Pragma": "no-cache",
            "Expires": "0",
        }

        # HSTS (HTTP Strict Transport Security) - Production only
        if settings.ENABLE_HSTS and settings.is_production:
            security_headers["Strict-Transport-Security"] = (
                f"max-age={settings.HSTS_MAX_AGE}; "
                "includeSubDomains; preload"
            )

        # Content Security Policy
        if settings.ENABLE_CSP:
            security_headers["Content-Security-Policy"] = settings.CSP_POLICY

        # API-specific headers
        security_headers.update({
            "X-API-Version": settings.APP_VERSION,
            "X-Content-Type-Options": "nosniff",
        })

        # Apply all headers
        for header, value in security_headers.items():
            response.headers[header] = value

        # Log security header application (debug only)
        if settings.DEBUG:
            logger.debug(f"Applied {len(security_headers)} security headers to {request.url.path}")

        return response

