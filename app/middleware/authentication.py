from datetime import datetime, timezone
from typing import Optional, Dict, Any
from fastapi import Request, HTTPException, status
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import Response
from jose import JWTError, jwt
from config import settings
import logging

logger = logging.getLogger(__name__)


class AuthenticationMiddleware(BaseHTTPMiddleware):

    # Public endpoints that don't require authentication
    PUBLIC_PATHS = [
        "/",
        "/health",
        "/docs",
        "/redoc",
        "/openapi.json",
        "/api/v1/auth/login",
        "/api/v1/auth/register",
        "/api/v1/auth/refresh",
        "/api/v1/auth/logout",
        "/api/v1/auth/verify-email",
        "/api/v1/auth/resend-verification",
        "/api/v1/auth/password-reset-request",
        "/api/v1/auth/password-reset",
    ]

    def __init__(self, app):
        super().__init__(app)
        if settings.JWT_ALGORITHM == "RS256":
            self.secret_key = settings.JWT_PUBLIC_KEY  # Public key for verification
            self.signing_key = settings.JWT_PRIVATE_KEY  # Private key for signing
        else:
            # For HS256, use SECRET_KEY
            self.secret_key = settings.SECRET_KEY
            self.signing_key = settings.SECRET_KEY
        self.algorithm = settings.JWT_ALGORITHM
        self.access_token_expire = settings.ACCESS_TOKEN_EXPIRE_HOURS

    async def dispatch(self, request: Request, call_next) -> Response:
        """Validate authentication for protected endpoints"""
        from fastapi.responses import JSONResponse

        # Skip authentication for public endpoints
        if self._is_public_path(request.url.path):
            return await call_next(request)

        # Skip for OPTIONS (preflight) requests
        if request.method == "OPTIONS":
            return await call_next(request)

        try:
            # Extract and validate token
            token = self._extract_token(request)
            if not token:
                return JSONResponse(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    content={"detail": "Missing authentication token"},
                    headers={"WWW-Authenticate": "Bearer"}
                )

            # Decode and validate token
            payload = self._decode_token(token)

            # Check if token is expired
            self._validate_expiration(payload)

            # Check token type (must be access token)
            self._validate_token_type(payload, "access")

            # Add user info to request state
            request.state.user_id = payload.get("sub")
            request.state.token_payload = payload

            # Check if token is about to expire and needs refresh
            if self._should_rotate_token(payload):
                logger.info(f"Token rotation recommended for user {payload.get('sub')}")
                # Could add a header suggesting token refresh

            # Process request
            response = await call_next(request)

            # Add token info to response headers (for debugging in dev)
            if settings.DEBUG:
                exp = payload.get("exp")
                if exp:
                    response.headers["X-Token-Expires"] = str(exp)

            return response


        except HTTPException as e:
            return JSONResponse(
                status_code=e.status_code,
                content={"detail": e.detail},
                headers=e.headers
            )
        except JWTError as e:
            logger.warning(f"JWT validation failed: {e}")
            return JSONResponse(
                status_code=status.HTTP_401_UNAUTHORIZED,
                content={"detail": "Invalid authentication token"},
                headers={"WWW-Authenticate": "Bearer"}
            )
        except Exception as e:
            logger.error(f"Authentication error: {e}", exc_info=True)
            return JSONResponse(
                status_code=status.HTTP_401_UNAUTHORIZED,
                content={"detail": "Authentication failed"},
                headers={"WWW-Authenticate": "Bearer"}
            )

    def _is_public_path(self, path: str) -> bool:
        """Check if path is public (doesn't require auth)"""
        # Exact match
        if path in self.PUBLIC_PATHS:
            return True

        # Check if path starts with public prefix
        public_prefixes = ["/docs", "/redoc", "/openapi.json", "/static", "/api/v1/integration"]
        return any(path.startswith(prefix) for prefix in public_prefixes)

    def _extract_token(self, request: Request) -> Optional[str]:
        """Extract JWT token from Authorization header"""
        auth_header = request.headers.get("Authorization")

        if not auth_header:
            return None

        # Check for Bearer token
        parts = auth_header.split()
        if len(parts) != 2 or parts[0].lower() != "bearer":
            logger.warning(f"Invalid authorization header format from {request.client}")
            return None

        return parts[1]

    def _decode_token(self, token: str) -> Dict[str, Any]:
        """Decode and validate JWT token"""
        try:
            payload = jwt.decode(
                token,
                self.secret_key,
                algorithms=[self.algorithm]
            )
            return payload
        except jwt.ExpiredSignatureError:
            logger.info("Token has expired")
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Token has expired",
                headers={"WWW-Authenticate": "Bearer"}
            )
        except jwt.JWTClaimsError as e:
            logger.warning(f"Invalid token claims: {e}")
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid token claims",
                headers={"WWW-Authenticate": "Bearer"}
            )
        except JWTError as e:
            logger.warning(f"Token decode error: {e}")
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Could not validate token",
                headers={"WWW-Authenticate": "Bearer"}
            )

    def _validate_expiration(self, payload: Dict[str, Any]) -> None:
        """Validate token expiration"""
        exp = payload.get("exp")
        if not exp:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Token missing expiration claim",
                headers={"WWW-Authenticate": "Bearer"}
            )

        # Check if token is expired
        exp_datetime = datetime.fromtimestamp(exp, tz=timezone.utc)
        now = datetime.now(timezone.utc)

        if exp_datetime < now:
            logger.info(f"Token expired at {exp_datetime}")
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Token has expired",
                headers={"WWW-Authenticate": "Bearer"}
            )

    def _validate_token_type(self, payload: Dict[str, Any], expected_type: str) -> None:
        """Validate token type (access or refresh)"""
        token_type = payload.get("type")

        if token_type != expected_type:
            logger.warning(f"Invalid token type: expected {expected_type}, got {token_type}")
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail=f"Invalid token type. Expected {expected_type} token",
                headers={"WWW-Authenticate": "Bearer"}
            )

    def _should_rotate_token(self, payload: Dict[str, Any]) -> bool:
        """Check if token should be rotated (refresh recommended)"""
        exp = payload.get("exp")
        if not exp:
            return False

        # Calculate time until expiration
        exp_datetime = datetime.fromtimestamp(exp, tz=timezone.utc)
        now = datetime.now(timezone.utc)
        time_until_expiry = (exp_datetime - now).total_seconds()

        # Recommend rotation if less than 5 minutes remaining
        rotation_threshold = 300  # 5 minutes

        return time_until_expiry < rotation_threshold
