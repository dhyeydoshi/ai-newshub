from typing import List, Optional
from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import Response
from starlette.datastructures import Headers
from config import settings
import logging

logger = logging.getLogger(__name__)


class CORSMiddleware(BaseHTTPMiddleware):

    def __init__(
        self,
        app,
        allow_origins: Optional[List[str]] = None,
        allow_methods: Optional[List[str]] = None,
        allow_headers: Optional[List[str]] = None,
        allow_credentials: bool = True,
        max_age: int = 600
    ):
        super().__init__(app)
        self.allow_origins = allow_origins or settings.CORS_ORIGINS
        self.allow_methods = allow_methods or settings.CORS_ALLOW_METHODS
        self.allow_headers = allow_headers or settings.CORS_ALLOW_HEADERS
        self.allow_credentials = allow_credentials
        self.max_age = max_age
        self.enabled = settings.CORS_ENABLED

        # Compile allowed origins for faster lookup
        self.allowed_origins_set = set(self.allow_origins) if "*" not in self.allow_origins else None

    async def dispatch(self, request: Request, call_next) -> Response:
        """Handle CORS for incoming requests"""

        if not self.enabled:
            return await call_next(request)

        # Get origin from request
        origin = request.headers.get("origin")

        # Check if origin is allowed
        is_allowed = self._is_origin_allowed(origin)

        # Handle preflight OPTIONS request
        if request.method == "OPTIONS":
            return self._handle_preflight(request, origin, is_allowed)

        # Process normal request
        response = await call_next(request)

        # Add CORS headers if origin is allowed
        if is_allowed and origin:
            self._add_cors_headers(response, origin)

        return response

    def _is_origin_allowed(self, origin: Optional[str]) -> bool:
        """Check if origin is in whitelist"""
        if not origin:
            return False

        # Allow all origins if "*" is in whitelist
        if "*" in self.allow_origins:
            return True

        # Check against whitelist
        if self.allowed_origins_set:
            return origin in self.allowed_origins_set

        return False

    def _handle_preflight(
        self,
        request: Request,
        origin: Optional[str],
        is_allowed: bool
    ) -> Response:
        """Handle CORS preflight OPTIONS request"""

        if not is_allowed:
            logger.warning(f"CORS preflight denied for origin: {origin}")
            return Response(
                content="Origin not allowed",
                status_code=403
            )

        # Get requested method and headers
        requested_method = request.headers.get("access-control-request-method")
        requested_headers = request.headers.get("access-control-request-headers")

        # Validate requested method ("*" allows all methods)
        if requested_method and "*" not in self.allow_methods and requested_method not in self.allow_methods:
            logger.warning(f"CORS method not allowed: {requested_method}")
            return Response(
                content="Method not allowed",
                status_code=405
            )

        # Create preflight response
        headers = {
            "Access-Control-Allow-Origin": origin,
            "Access-Control-Allow-Methods": ", ".join(self.allow_methods),
            "Access-Control-Max-Age": str(self.max_age),
            "Vary": "Origin"
        }

        # Add allowed headers
        if "*" in self.allow_headers:
            if requested_headers:
                headers["Access-Control-Allow-Headers"] = requested_headers
            else:
                headers["Access-Control-Allow-Headers"] = "*"
        else:
            headers["Access-Control-Allow-Headers"] = ", ".join(self.allow_headers)

        # Add credentials header
        if self.allow_credentials:
            headers["Access-Control-Allow-Credentials"] = "true"

        logger.debug(f"CORS preflight approved for {origin}")

        return Response(
            status_code=200,
            headers=headers
        )

    def _add_cors_headers(self, response: Response, origin: str) -> None:
        """Add CORS headers to response"""

        response.headers["Access-Control-Allow-Origin"] = origin
        response.headers["Vary"] = "Origin"

        if self.allow_credentials:
            response.headers["Access-Control-Allow-Credentials"] = "true"

        # Expose headers that client can access
        response.headers["Access-Control-Expose-Headers"] = (
            "X-RateLimit-Limit, X-RateLimit-Remaining, X-RateLimit-Reset, "
            "X-Process-Time, X-API-Version"
        )

