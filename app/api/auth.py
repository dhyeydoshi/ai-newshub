"""
Authentication Router
Complete JWT-based authentication system with security features
"""
from fastapi import APIRouter, Depends, HTTPException, status, Request, Response
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.core.database import get_db
from app.models.user import User, LoginAttempt, UserSession
from app.schemas.auth import (
    UserRegister,
    UserLogin,
    TokenRefresh,
    PasswordResetRequest,
    PasswordReset,
    PasswordChange,
    EmailVerification,
    ResendVerification,
    UserResponse,
    LoginResponse,
    TokenResponse,
    MessageResponse,
    UserDetailResponse,
    SessionResponse
)
from app.services.auth_service import auth_service
from app.core.jwt import jwt_manager
from app.core.password import pwd_hasher
from config import settings
import logging

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/auth", tags=["Authentication"])


# ============================================================================
# HELPER DEPENDENCIES
# ============================================================================

from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from fastapi import Security

security = HTTPBearer()


async def get_current_user_id(
    credentials: HTTPAuthorizationCredentials = Security(security),
    db: AsyncSession = Depends(get_db)
) -> str:
    """
    Extract and validate user ID from JWT token

    Returns user_id for use in protected endpoints
    """
    token = credentials.credentials
    payload = jwt_manager.decode_token(token)

    # Validate token type
    if payload.get("type") != "access":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token type"
        )

    user_id = payload.get("sub")
    if not user_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token: missing subject"
        )

    # Verify user still exists and is active
    result = await db.execute(
        select(User).where(User.user_id == user_id)
    )
    user = result.scalar_one_or_none()

    if not user or not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found or inactive"
        )

    return user_id


# ============================================================================
# REGISTRATION & EMAIL VERIFICATION
# ============================================================================

@router.post("/register", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
async def register(
    user_data: UserRegister,
    db: AsyncSession = Depends(get_db)
):
    """
    Register a new user

    Security Features:
    - Password strength validation (zxcvbn)
    - Email uniqueness check
    - Username uniqueness check
    - Argon2 password hashing
    - Email verification token generation
    """
    user, verification_token = await auth_service.register_user(user_data, db)

    return UserResponse.model_validate(user)


@router.post("/verify-email", response_model=MessageResponse)
async def verify_email(
    verification_data: EmailVerification,
    db: AsyncSession = Depends(get_db)
):
    """
    Verify user email with token

    Required for account activation if EMAIL_VERIFICATION_REQUIRED is enabled
    """
    user = await auth_service.verify_email(verification_data.token, db)

    return MessageResponse(
        message="Email verified successfully. You can now log in.",
        success=True
    )


@router.post("/resend-verification", response_model=MessageResponse)
async def resend_verification(
    data: ResendVerification,
    db: AsyncSession = Depends(get_db)
):
    """
    Resend email verification link
    """
    result = await db.execute(
        select(User).where(User.email == data.email)
    )
    user = result.scalar_one_or_none()

    if user and not user.is_verified:
        from datetime import datetime, timezone, timedelta
        from app.services.email_service import email_service

        # Generate new token
        verification_token = pwd_hasher.generate_secure_token(32)
        user.verification_token = verification_token
        user.verification_token_expires = datetime.now(timezone.utc) + timedelta(
            hours=settings.EMAIL_VERIFICATION_TOKEN_EXPIRE_HOURS
        )

        await db.commit()

        # Send email
        await email_service.send_verification_email(
            user.email,
            user.username,
            verification_token
        )

    # Always return success to prevent user enumeration
    return MessageResponse(
        message="If the email exists and is not verified, a verification link has been sent.",
        success=True
    )


# ============================================================================
# LOGIN & TOKEN MANAGEMENT
# ============================================================================

@router.post("/login", response_model=LoginResponse)
async def login(
    login_data: UserLogin,
    request: Request,
    response: Response,
    db: AsyncSession = Depends(get_db)
):
    """
    Login with email and password

    Security Features:
    - Account lockout after 5 failed attempts
    - 30-minute lockout duration
    - Email verification requirement
    - Argon2 password verification
    - JWT token generation (RS256)
    - Refresh token in httpOnly cookie
    - Session tracking
    """
    user, access_token, refresh_token, cookie_config = await auth_service.login(
        login_data,
        request,
        db
    )

    # Set refresh token in httpOnly cookie
    response.set_cookie(
        key=cookie_config["key"],
        value=cookie_config["value"],
        max_age=cookie_config["max_age"],
        httponly=cookie_config["httponly"],
        secure=cookie_config["secure"],
        samesite=cookie_config["samesite"],
        path=cookie_config["path"]
    )

    return LoginResponse(
        user=UserResponse.model_validate(user),
        access_token=access_token,
        token_type="bearer",
        expires_in=settings.ACCESS_TOKEN_EXPIRE_HOURS * 3600,
        refresh_token=None  # In cookie, not in response
    )


@router.post("/refresh", response_model=TokenResponse)
async def refresh_token(
    response: Response,
    request: Request,
    token_data: TokenRefresh = None,
    db: AsyncSession = Depends(get_db)
):
    """
    Refresh access token using refresh token

    Token Rotation:
    - Old refresh token is invalidated
    - New refresh token is issued
    - Stored in httpOnly cookie
    """
    # Get refresh token from cookie or body
    refresh_token = request.cookies.get("refresh_token")
    if not refresh_token and token_data:
        refresh_token = token_data.refresh_token

    if not refresh_token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Refresh token not found"
        )

    # Refresh tokens
    new_access_token, new_refresh_token = await auth_service.refresh_token(
        refresh_token,
        db
    )
    cookie_max_age = request.cookies.get("refresh_token_max_age", 24 * 60 * 60)


    # Update refresh token in cookie
    response.set_cookie(
        key="refresh_token",
        value=new_refresh_token,
        max_age=int(cookie_max_age),
        httponly=True,
        secure=settings.ENVIRONMENT == "production",
        samesite="lax",
        path="/"
    )

    return TokenResponse(
        access_token=new_access_token,
        token_type="bearer",
        expires_in=settings.ACCESS_TOKEN_EXPIRE_HOURS * 3600,
        refresh_token=None
    )


@router.post("/logout", response_model=MessageResponse)
async def logout(
    response: Response,
    request: Request,
    db: AsyncSession = Depends(get_db)
):
    """
    Logout and revoke session
    """
    # Get refresh token from cookie
    refresh_token = request.cookies.get("refresh_token")

    if refresh_token:
        try:
            # Decode token to get session
            payload = jwt_manager.decode_token(refresh_token)
            session_id = payload.get("sid")

            if session_id:
                # Revoke session
                from app.models.user import UserSession
                from datetime import datetime, timezone
                from sqlalchemy import and_

                result = await db.execute(
                    select(UserSession).where(
                        and_(
                            UserSession.session_id == session_id,
                            UserSession.is_active == True
                        )
                    )
                )
                session = result.scalar_one_or_none()

                if session:
                    session.is_active = False
                    session.revoked_at = datetime.now(timezone.utc)
                    await db.commit()
        except Exception as e:
            logger.warning(f"Error revoking session: {e}")

    # Clear cookie
    response.delete_cookie(
        key="refresh_token",
        path="/",
        httponly=True,
        secure=settings.ENVIRONMENT == "production",
        samesite="lax"
)

    return MessageResponse(
        message="Logged out successfully",
        success=True
    )


# ============================================================================
# PASSWORD MANAGEMENT
# ============================================================================

@router.post("/password-reset-request", response_model=MessageResponse)
async def request_password_reset(
    data: PasswordResetRequest,
    db: AsyncSession = Depends(get_db)
):
    """
    Request password reset email

    Always returns success to prevent user enumeration
    """
    await auth_service.request_password_reset(data.email, db)

    return MessageResponse(
        message="If the email exists, a password reset link has been sent.",
        success=True
    )


@router.post("/password-reset", response_model=MessageResponse)
async def reset_password(
    data: PasswordReset,
    db: AsyncSession = Depends(get_db)
):
    """
    Reset password with token

    Security Features:
    - Token expiration (1 hour)
    - Password strength validation
    - All sessions revoked after reset
    """
    await auth_service.reset_password(data.token, data.new_password, db)

    return MessageResponse(
        message="Password reset successfully. Please log in with your new password.",
        success=True
    )


@router.post("/change-password", response_model=MessageResponse)
async def change_password(
    data: PasswordChange,
    request: Request,
    db: AsyncSession = Depends(get_db)
):
    """
    Change password for authenticated user

    Requires current password verification
    """
    user_id = request.state.user_id

    await auth_service.change_password(
        user_id,
        data.current_password,
        data.new_password,
        db
    )

    return MessageResponse(
        message="Password changed successfully",
        success=True
    )


# ============================================================================
# USER PROFILE
# ============================================================================

@router.get("/me", response_model=UserDetailResponse)
async def get_current_user(
    user_id: str = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db)
):
    """
    Get current authenticated user profile
    """
    result = await db.execute(
        select(User).where(User.user_id == user_id)
    )
    user = result.scalar_one_or_none()

    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found"
        )

    # Count active sessions
    from app.models.user import UserSession
    from sqlalchemy import func

    session_count = await db.execute(
        select(func.count(UserSession.session_id))
        .where(UserSession.user_id == user.user_id)
        .where(UserSession.is_active == True)
    )
    active_sessions = session_count.scalar() or 0

    return UserDetailResponse(
        **user.__dict__,
        active_sessions=active_sessions
    )


@router.get("/sessions", response_model=list[SessionResponse])
async def get_user_sessions(
    user_id: str = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db)
):
    """
    Get all active sessions for current user
    """
    from app.models.user import UserSession

    result = await db.execute(
        select(UserSession)
        .where(UserSession.user_id == user_id)
        .where(UserSession.is_active == True)
        .order_by(UserSession.created_at.desc())
    )
    sessions = result.scalars().all()

    return [SessionResponse.model_validate(session) for session in sessions]


@router.delete("/sessions/{session_id}", response_model=MessageResponse)
async def revoke_session(
    session_id: str,
    user_id: str = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db)
):
    """
    Revoke a specific session
    """
    from app.models.user import UserSession
    from datetime import datetime, timezone
    from sqlalchemy import and_

    result = await db.execute(
        select(UserSession).where(
            and_(
                UserSession.session_id == session_id,
                UserSession.user_id == user_id,
                UserSession.is_active == True
            )
        )
    )
    session = result.scalar_one_or_none()

    if not session:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Session not found"
        )

    session.is_active = False
    session.revoked_at = datetime.now(timezone.utc)
    await db.commit()

    return MessageResponse(
        message="Session revoked successfully",
        success=True
    )
