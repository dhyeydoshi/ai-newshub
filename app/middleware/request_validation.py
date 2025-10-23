"""
Request Validation Middleware
Validates request size, content type, and logs requests safely
"""
import time
import json
from typing import Set
from fastapi import Request, HTTPException, status
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import Response, JSONResponse
from config import settings
import logging

logger = logging.getLogger(__name__)


class RequestValidationMiddleware(BaseHTTPMiddleware):
    """
    Validates incoming requests for security
    - Size limits
    - Content-type validation
    - Request logging without sensitive data
    """

    # Sensitive headers to exclude from logs
    SENSITIVE_HEADERS: Set[str] = {
        "authorization",
        "cookie",
        "x-api-key",
        "x-auth-token",
        "proxy-authorization"
    }

    # Sensitive fields to redact from body
    SENSITIVE_FIELDS: Set[str] = {
        "password",
        "token",
        "secret",
        "api_key",
        "access_token",
        "refresh_token",
        "credit_card",
        "ssn",
        "cvv"
    }

    def __init__(self, app):
        super().__init__(app)
        self.max_size = settings.max_request_size_bytes
        self.allowed_types = settings.ALLOWED_CONTENT_TYPES
        self.log_requests = settings.LOG_REQUESTS

    async def dispatch(self, request: Request, call_next) -> Response:
        """Validate and process request"""

        start_time = time.time()

        # Skip validation for health checks
        if request.url.path in ["/health", "/docs", "/redoc", "/openapi.json"]:
            return await call_next(request)

        try:
            # 1. Validate request size
            await self._validate_size(request)

            # 2. Validate content type for POST/PUT/PATCH
            if request.method in ["POST", "PUT", "PATCH"]:
                await self._validate_content_type(request)

            # 3. Log request (without sensitive data)
            if self.log_requests:
                await self._log_request(request)

            # Process request
            response = await call_next(request)

            # Add processing time header
            process_time = time.time() - start_time
            response.headers["X-Process-Time"] = f"{process_time:.4f}"

            # Log response
            if self.log_requests:
                self._log_response(request, response, process_time)

            return response

        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"Request validation error: {e}", exc_info=True)
            return JSONResponse(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                content={"detail": "Internal server error"}
            )

    async def _validate_size(self, request: Request) -> None:
        """Validate request size doesn't exceed limit"""
        content_length = request.headers.get("content-length")

        if content_length:
            size = int(content_length)
            if size > self.max_size:
                logger.warning(
                    f"Request size {size} bytes exceeds limit {self.max_size} bytes "
                    f"from {request.client.host if request.client else 'unknown'}"
                )
                raise HTTPException(
                    status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                    detail=f"Request body too large. Maximum size is {settings.MAX_REQUEST_SIZE_MB}MB"
                )

    async def _validate_content_type(self, request: Request) -> None:
        """Validate content type is allowed"""
        content_type = request.headers.get("content-type", "").split(";")[0].strip()

        if not content_type:
            return  # Allow empty content type for GET requests

        # Check if content type is allowed
        allowed = any(
            content_type.startswith(allowed_type)
            for allowed_type in self.allowed_types
        )

        if not allowed:
            logger.warning(
                f"Invalid content type '{content_type}' from "
                f"{request.client.host if request.client else 'unknown'}"
            )
            raise HTTPException(
                status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
                detail=f"Content type '{content_type}' not supported. "
                       f"Allowed types: {', '.join(self.allowed_types)}"
            )

    async def _log_request(self, request: Request) -> None:
        """Log request safely without sensitive data"""
        try:
            # Safe headers (exclude sensitive ones)
            safe_headers = {
                k: v for k, v in request.headers.items()
                if k.lower() not in self.SENSITIVE_HEADERS
            }

            # Build log entry
            log_data = {
                "method": request.method,
                "path": request.url.path,
                "query_params": str(request.query_params),
                "client_ip": request.client.host if request.client else "unknown",
                "user_agent": request.headers.get("user-agent", "unknown"),
                "headers": safe_headers
            }

            # Add sanitized body for POST/PUT/PATCH (if JSON)
            if request.method in ["POST", "PUT", "PATCH"]:
                content_type = request.headers.get("content-type", "")
                if "application/json" in content_type:
                    try:
                        # Read body (need to store for later use)
                        body = await request.body()
                        if body:
                            body_json = json.loads(body)
                            sanitized_body = self._sanitize_data(body_json)
                            log_data["body"] = sanitized_body
                    except Exception as e:
                        log_data["body"] = "<unable to parse>"

            logger.info(f"Request: {json.dumps(log_data)}")

        except Exception as e:
            logger.error(f"Error logging request: {e}")

    def _log_response(self, request: Request, response: Response, process_time: float) -> None:
        """Log response information"""
        try:
            log_data = {
                "method": request.method,
                "path": request.url.path,
                "status_code": response.status_code,
                "process_time": f"{process_time:.4f}s"
            }

            logger.info(f"Response: {json.dumps(log_data)}")

        except Exception as e:
            logger.error(f"Error logging response: {e}")

    def _sanitize_data(self, data: any) -> any:
        """Recursively sanitize sensitive data"""
        if isinstance(data, dict):
            return {
                k: "***REDACTED***" if k.lower() in self.SENSITIVE_FIELDS
                else self._sanitize_data(v)
                for k, v in data.items()
            }
        elif isinstance(data, list):
            return [self._sanitize_data(item) for item in data]
        else:
            return data

