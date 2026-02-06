from datetime import datetime, timezone, timedelta
from typing import Optional, Dict, Any
from jose import jwt, JWTError
from fastapi import HTTPException, status
from config import settings
import logging

logger = logging.getLogger(__name__)


class JWTManager:
    """JWT token manager with RS256 algorithm"""

    def __init__(self):
        self.algorithm = settings.JWT_ALGORITHM
        self.private_key = settings.JWT_PRIVATE_KEY
        self.public_key = settings.JWT_PUBLIC_KEY
        self.access_token_expire = settings.ACCESS_TOKEN_EXPIRE_HOURS
        self.refresh_token_expire = settings.REFRESH_TOKEN_EXPIRE_DAYS

        if not self.private_key or not self.public_key:
            logger.warning("JWT keys not configured. Tokens will not work properly.")

    def create_access_token(
        self,
        subject: str,
        additional_claims: Optional[Dict[str, Any]] = None
    ) -> str:
        now = datetime.now(timezone.utc)
        expire = now + timedelta(hours=self.access_token_expire)

        claims = {
            "sub": subject,
            "exp": expire,
            "iat": now,
            "type": "access",
            "jti": self._generate_jti()
        }

        if additional_claims:
            claims.update(additional_claims)

        try:
            token = jwt.encode(
                claims,
                self.private_key,
                algorithm=self.algorithm
            )
            return token
        except Exception as e:
            logger.error(f"Failed to create access token: {e}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to create token"
            )

    def create_refresh_token(
        self,
        subject: str,
        session_id: Optional[str] = None
    ) -> str:
        now = datetime.now(timezone.utc)
        expire = now + timedelta(days=self.refresh_token_expire)

        claims = {
            "sub": subject,
            "exp": expire,
            "iat": now,
            "type": "refresh",
            "jti": self._generate_jti()
        }

        if session_id:
            claims["sid"] = session_id

        try:
            token = jwt.encode(
                claims,
                self.private_key,
                algorithm=self.algorithm
            )
            return token
        except Exception as e:
            logger.error(f"Failed to create refresh token: {e}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to create token"
            )

    def decode_token(self, token: str) -> Dict[str, Any]:
        try:
            payload = jwt.decode(
                token,
                self.public_key,
                algorithms=[self.algorithm]
            )
            return payload
        except jwt.ExpiredSignatureError:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Token has expired",
                headers={"WWW-Authenticate": "Bearer"}
            )
        except jwt.JWTClaimsError:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid token claims",
                headers={"WWW-Authenticate": "Bearer"}
            )
        except JWTError as e:
            logger.warning(f"JWT decode error: {e}")
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Could not validate token",
                headers={"WWW-Authenticate": "Bearer"}
            )

    def validate_token_type(self, payload: Dict[str, Any], expected_type: str) -> None:
        token_type = payload.get("type")
        if token_type != expected_type:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail=f"Invalid token type. Expected {expected_type} token",
                headers={"WWW-Authenticate": "Bearer"}
            )

    def get_token_subject(self, token: str) -> str:
        payload = self.decode_token(token)
        subject = payload.get("sub")
        if not subject:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid token: missing subject"
            )
        return subject

    def get_token_expiry(self, token: str) -> datetime:
        payload = self.decode_token(token)
        exp = payload.get("exp")
        if not exp:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid token: missing expiration"
            )
        return datetime.fromtimestamp(exp, tz=timezone.utc)

    @staticmethod
    def _generate_jti() -> str:
        """Generate unique token ID"""
        from app.core.password import pwd_hasher
        return pwd_hasher.generate_secure_token(16)


# Global JWT manager instance
jwt_manager = JWTManager()

