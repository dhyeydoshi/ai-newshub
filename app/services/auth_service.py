import uuid
from datetime import datetime, timezone, timedelta
from typing import Optional, Tuple
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_, or_
from fastapi import HTTPException, status, Request
import logging

from app.models.user import User, UserSession, LoginAttempt
from app.schemas.auth import UserRegister, UserLogin
from app.core.password import pwd_hasher
from app.core.password_validator import password_validator
from app.core.jwt import jwt_manager
from app.services.email_service import email_service
from config import settings

logger = logging.getLogger(__name__)


class AuthService:
    """Authentication service with comprehensive security features"""

    async def register_user(
        self,
        user_data: UserRegister,
        db: AsyncSession
    ) -> Tuple[User, str]:
        # Check if user already exists
        result = await db.execute(
            select(User).where(
                or_(
                    User.email == user_data.email,
                    User.username == user_data.username
                )
            )
        )
        existing_user = result.scalar_one_or_none()

        if existing_user:
            if existing_user.email == user_data.email:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Email already registered"
                )
            else:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Username already taken"
                )

        # Validate password strength
        user_inputs = [user_data.email, user_data.username]
        if user_data.full_name:
            user_inputs.append(user_data.full_name)

        strength = password_validator.validate_password_strength(
            user_data.password,
            user_inputs=user_inputs
        )

        if not strength['valid']:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Password too weak: {strength['feedback']}",
                headers={"X-Password-Suggestions": ", ".join(strength['suggestions'])}
            )

        # Hash password
        password_hash = pwd_hasher.hash_password(user_data.password)

        # Generate verification token
        verification_token = pwd_hasher.generate_secure_token(32)
        verification_expires = datetime.now(timezone.utc) + timedelta(
            hours=settings.EMAIL_VERIFICATION_TOKEN_EXPIRE_HOURS
        )

        # Create user
        new_user = User(
            email=user_data.email,
            username=user_data.username,
            password_hash=password_hash,
            full_name=user_data.full_name,
            data_processing_consent=user_data.data_processing_consent,
            consent_date=datetime.now(timezone.utc) if user_data.data_processing_consent else None,
            verification_token=verification_token,
            verification_token_expires=verification_expires,
            is_verified=not settings.EMAIL_VERIFICATION_REQUIRED,
            last_password_change=datetime.now(timezone.utc)
        )

        db.add(new_user)
        await db.commit()
        await db.refresh(new_user)

        logger.info(f"User registered: {new_user.username} ({new_user.email})")

        # Send verification email if required
        if settings.EMAIL_VERIFICATION_REQUIRED:
            await email_service.send_verification_email(
                new_user.email,
                new_user.username,
                verification_token
            )

        return new_user, verification_token

    async def verify_email(
        self,
        token: str,
        db: AsyncSession
    ) -> User:
        result = await db.execute(
            select(User).where(
                and_(
                    User.verification_token == token,
                    User.is_verified == False
                )
            )
        )
        user = result.scalar_one_or_none()

        if not user:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid or expired verification token"
            )

        # Check if token expired
        if user.verification_token_expires < datetime.now(timezone.utc):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Verification token has expired. Please request a new one."
            )

        # Verify user
        user.is_verified = True
        user.email_verified_at = datetime.now(timezone.utc)
        user.verification_token = None
        user.verification_token_expires = None

        await db.commit()
        await db.refresh(user)

        logger.info(f"Email verified for user: {user.username}")

        return user

    async def login(
        self,
        login_data: UserLogin,
        request: Request,
        db: AsyncSession
    ) -> Tuple[User, str, str, dict]:
        # Get user
        result = await db.execute(
            select(User).where(User.email == login_data.email)
        )
        user = result.scalar_one_or_none()

        # Record login attempt
        ip_address = request.client.host if request.client else "unknown"
        user_agent = request.headers.get("user-agent", "unknown")

        if not user:
            # Record failed attempt
            await self._record_login_attempt(
                login_data.email,
                ip_address,
                user_agent,
                False,
                "User not found",
                db
            )
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Incorrect email or password"
            )

        # Check if account is locked
        if user.is_locked and user.locked_until:
            if user.locked_until > datetime.now(timezone.utc):
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail=f"Account locked until {user.locked_until.isoformat()}"
                )
            else:
                # Unlock account if lockout period has passed
                user.is_locked = False
                user.locked_until = None
                user.failed_login_attempts = 0

        # Check if account is active
        if not user.is_active:
            await self._record_login_attempt(
                login_data.email,
                ip_address,
                user_agent,
                False,
                "Account inactive",
                db
            )
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Account is inactive"
            )

        # Check if email is verified
        if settings.EMAIL_VERIFICATION_REQUIRED and not user.is_verified:
            await self._record_login_attempt(
                login_data.email,
                ip_address,
                user_agent,
                False,
                "Email not verified",
                db
            )
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Please verify your email before logging in"
            )

        # Verify password
        if not pwd_hasher.verify_password(login_data.password, user.password_hash):
            # Increment failed attempts
            user.failed_login_attempts += 1
            user.last_failed_login = datetime.now(timezone.utc)

            # Lock account if max attempts reached
            if user.failed_login_attempts >= settings.MAX_LOGIN_ATTEMPTS:
                user.is_locked = True
                user.locked_until = datetime.now(timezone.utc) + timedelta(
                    minutes=settings.ACCOUNT_LOCKOUT_DURATION_MINUTES
                )

                # Send email notification
                await email_service.send_account_locked_email(
                    user.email,
                    user.username,
                    user.locked_until.isoformat()
                )

                await db.commit()

                logger.warning(f"Account locked: {user.email} after {settings.MAX_LOGIN_ATTEMPTS} failed attempts")

                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail=f"Account locked due to too many failed login attempts. Try again after {settings.ACCOUNT_LOCKOUT_DURATION_MINUTES} minutes."
                )

            await db.commit()

            await self._record_login_attempt(
                login_data.email,
                ip_address,
                user_agent,
                False,
                "Invalid password",
                db
            )

            remaining_attempts = settings.MAX_LOGIN_ATTEMPTS - user.failed_login_attempts
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail=f"Incorrect email or password. {remaining_attempts} attempts remaining."
            )

        # Check if password needs rehashing
        if pwd_hasher.needs_rehash(user.password_hash):
            user.password_hash = pwd_hasher.hash_password(login_data.password)

        # Reset failed login attempts on successful login
        user.failed_login_attempts = 0
        user.last_failed_login = None
        user.last_login_at = datetime.now(timezone.utc)

        # Create session
        session = await self._create_session(
            user,
            ip_address,
            user_agent,
            login_data.remember_me,
            db
        )

        # Generate tokens
        access_token = jwt_manager.create_access_token(
            subject=str(user.user_id),
            additional_claims={
                "email": user.email,
                "username": user.username
            }
        )

        refresh_token = jwt_manager.create_refresh_token(
            subject=str(user.user_id),
            session_id=str(session.session_id)
        )

        cookie_config = self._create_remember_me_cookie(refresh_token, login_data.remember_me)

        await db.commit()

        await self._record_login_attempt(
            login_data.email,
            ip_address,
            user_agent,
            True,
            None,
            db
        )

        logger.info(f"User logged in: {user.username}")

        return user, access_token, refresh_token, cookie_config

    async def refresh_token(
        self,
        refresh_token: str,
        db: AsyncSession
    ) -> Tuple[str, str]:
        # Decode refresh token
        payload = jwt_manager.decode_token(refresh_token)
        jwt_manager.validate_token_type(payload, "refresh")

        user_id = payload.get("sub")
        session_id = payload.get("sid")
        jti = payload.get("jti")

        if not user_id or not session_id or not jti:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid refresh token"
            )

        # Get session
        result = await db.execute(
            select(UserSession).where(
                and_(
                    UserSession.session_id == session_id,
                    # UserSession.refresh_token_jti == jti,
                    UserSession.is_active == True
                )
            )
        )
        session = result.scalar_one_or_none()

        if not session:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Session not found or revoked"
            )

        # Check if session expired
        if session.expires_at < datetime.now(timezone.utc):
            session.is_active = False
            await db.commit()
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Session has expired. Please login again."
            )

        # Get user
        result = await db.execute(
            select(User).where(User.user_id == user_id)
        )
        user = result.scalar_one_or_none()

        if not user or not user.is_active:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="User not found or inactive"
            )

        # Create new tokens (token rotation)
        new_access_token = jwt_manager.create_access_token(
            subject=str(user.user_id),
            additional_claims={
                "email": user.email,
                "username": user.username
            }
        )

        new_refresh_token = jwt_manager.create_refresh_token(
            subject=str(user.user_id),
            session_id=str(session.session_id)
        )

        # Update session with new refresh token JTI
        new_payload = jwt_manager.decode_token(new_refresh_token)
        # session.refresh_token_jti = new_payload.get("jti")
        session.last_used_at = datetime.now(timezone.utc)

        await db.commit()

        logger.info(f"Token refreshed for user: {user.username}")

        return new_access_token, new_refresh_token

    async def request_password_reset(
        self,
        email: str,
        db: AsyncSession
    ) -> bool:
        result = await db.execute(
            select(User).where(User.email == email)
        )
        user = result.scalar_one_or_none()

        if user and user.is_active:
            # Generate reset token
            reset_token = pwd_hasher.generate_secure_token(32)
            reset_expires = datetime.now(timezone.utc) + timedelta(
                hours=settings.PASSWORD_RESET_TOKEN_EXPIRE_HOURS
            )

            user.reset_token = reset_token
            user.reset_token_expires = reset_expires

            await db.commit()

            # Send reset email
            await email_service.send_password_reset_email(
                user.email,
                user.username,
                reset_token
            )

            logger.info(f"Password reset requested for: {user.email}")

        # Always return True to prevent user enumeration
        return True

    async def change_password(
        self,
        user_id: str,
        current_password: str,
        new_password: str,
        db: AsyncSession
    ) -> User:
        result = await db.execute(
            select(User).where(
                and_(
                    User.user_id == user_id,
                    User.is_active == True
                )
            )
        )
        user = result.scalar_one_or_none()

        if not user:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="User not found"
            )

        if not pwd_hasher.verify_password(current_password, user.password_hash):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Current password is incorrect"
            )

        if current_password == new_password:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="New password must be different from current password"
            )

        user_inputs = [user.email, user.username]
        if user.full_name:
            user_inputs.append(user.full_name)

        strength = password_validator.validate_password_strength(
            new_password,
            user_inputs=user_inputs
        )
        if not strength['valid']:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Password too weak: {strength['feedback']}"
            )

        user.password_hash = pwd_hasher.hash_password(new_password)
        user.last_password_change = datetime.now(timezone.utc)

        await db.commit()
        await db.refresh(user)

        logger.info(f"Password changed for user: {user.username}")
        return user

    async def reset_password(
        self,
        token: str,
        new_password: str,
        db: AsyncSession
    ) -> User:
        result = await db.execute(
            select(User).where(User.reset_token == token)
        )
        user = result.scalar_one_or_none()

        if not user:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid or expired reset token"
            )

        # Check if token expired
        if user.reset_token_expires < datetime.now(timezone.utc):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Reset token has expired. Please request a new one."
            )

        # Validate new password
        user_inputs = [user.email, user.username]
        if user.full_name:
            user_inputs.append(user.full_name)

        strength = password_validator.validate_password_strength(
            new_password,
            user_inputs=user_inputs
        )

        if not strength['valid']:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Password too weak: {strength['feedback']}"
            )

        # Update password
        user.password_hash = pwd_hasher.hash_password(new_password)
        user.reset_token = None
        user.reset_token_expires = None
        user.last_password_change = datetime.now(timezone.utc)

        # Revoke all sessions for security
        await db.execute(
            select(UserSession).where(
                and_(
                    UserSession.user_id == user.user_id,
                    UserSession.is_active == True
                )
            )
        )
        sessions = (await db.execute(
            select(UserSession).where(UserSession.user_id == user.user_id)
        )).scalars().all()

        for session in sessions:
            session.is_active = False
            session.revoked_at = datetime.now(timezone.utc)

        await db.commit()
        await db.refresh(user)

        logger.info(f"Password reset for user: {user.username}")

        return user

    async def _create_session(
        self,
        user: User,
        ip_address: str,
        user_agent: str,
        remember_me: bool,
        db: AsyncSession
    ) -> UserSession:
        """Create new user session"""
        # Calculate expiry
        if remember_me:
            expires_at = datetime.now(timezone.utc) + timedelta(
                days=settings.REFRESH_TOKEN_EXPIRE_DAYS
            )
        else:
            expires_at = datetime.now(timezone.utc) + timedelta(days=1)

        # Create session
        session = UserSession(
            user_id=user.user_id,
            session_id=uuid.uuid4(),
            # refresh_token_jti=pwd_hasher.generate_secure_token(16),
            ip_address=ip_address,
            user_agent=user_agent,
            expires_at=expires_at
        )

        db.add(session)

        # Limit active sessions
        await self._cleanup_old_sessions(user.user_id, db)

        return session

    def _create_remember_me_cookie(self, refresh_token: str, remember_me: bool) -> dict:
        """Create cookie configuration for refresh token"""
        if remember_me:
            max_age = settings.REFRESH_TOKEN_EXPIRE_DAYS * 24 * 60 * 60  # Convert days to seconds
        else:
            max_age = 24 * 60 * 60  # 1 day for non-remember-me sessions

        return {
            "key": "refresh_token",
            "value": refresh_token,
            "max_age": max_age,
            "httponly": True,
            "secure": settings.ENVIRONMENT == "production",
            "samesite": "lax",
            "path": "/"
        }

    async def _cleanup_old_sessions(
        self,
        user_id: str,
        db: AsyncSession
    ) -> None:
        """Clean up old sessions, keeping only MAX_ACTIVE_SESSIONS"""
        result = await db.execute(
            select(UserSession)
            .where(
                and_(
                    UserSession.user_id == user_id,
                    UserSession.is_active == True
                )
            )
            .order_by(UserSession.created_at.desc())
        )
        sessions = result.scalars().all()

        if len(sessions) >= settings.MAX_ACTIVE_SESSIONS:
            # Revoke oldest sessions
            for session in sessions[settings.MAX_ACTIVE_SESSIONS - 1:]:
                session.is_active = False
                session.revoked_at = datetime.now(timezone.utc)

    async def _record_login_attempt(
        self,
        email: str,
        ip_address: str,
        user_agent: str,
        success: bool,
        failure_reason: Optional[str],
        db: AsyncSession
    ) -> None:
        """Record login attempt for security monitoring"""
        attempt = LoginAttempt(
            email=email,
            ip_address=ip_address,
            user_agent=user_agent,
            success=success,
            failure_reason=failure_reason
        )
        db.add(attempt)
        await db.commit()


# Global auth service instance
auth_service = AuthService()

