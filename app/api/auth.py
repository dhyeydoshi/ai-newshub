from fastapi import APIRouter, Depends, HTTPException, status, Request, Response
from typing import List
from html import escape
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update, and_
from datetime import datetime, timezone

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
    DeveloperContactRequest,
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
from app.dependencies.rate_limit import RateLimitPresets
from config import settings
import logging

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/auth", tags=["Authentication"])


def _clear_refresh_cookie(response: Response) -> None:
    """Clear refresh-token cookie from client."""
    response.delete_cookie(
        key="refresh_token",
        path="/",
        httponly=True,
        secure=settings.ENVIRONMENT == "production",
        samesite="lax"
    )


from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from fastapi import Security

security = HTTPBearer()


async def get_current_user_id(
    credentials: HTTPAuthorizationCredentials = Security(security),
    db: AsyncSession = Depends(get_db)
) -> str:
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


@router.post("/register", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
async def register(
    user_data: UserRegister,
    request: Request,
    db: AsyncSession = Depends(get_db),
    _rate_limit=Depends(RateLimitPresets.strict)
):
    user, verification_token = await auth_service.register_user(user_data, db)

    return UserResponse.model_validate(user)


@router.post("/verify-email", response_model=MessageResponse)
async def verify_email(
    verification_data: EmailVerification,
    request: Request,
    db: AsyncSession = Depends(get_db),
    _rate_limit=Depends(RateLimitPresets.strict)
):
    user = await auth_service.verify_email(verification_data.token, db)

    return MessageResponse(
        message="Email verified successfully. You can now log in.",
        success=True
    )


@router.post("/resend-verification", response_model=MessageResponse)
async def resend_verification(
    data: ResendVerification,
    request: Request,
    db: AsyncSession = Depends(get_db),
    _rate_limit=Depends(RateLimitPresets.strict)
):
    result = await db.execute(
        select(User).where(User.email == data.email)
    )
    user = result.scalar_one_or_none()

    if user and not user.is_verified:
        from datetime import datetime, timezone, timedelta
        from app.services.email_service import email_service

        user_email = user.email
        username = user.username

        # Generate new token
        verification_token = pwd_hasher.generate_secure_token(32)
        user.verification_token = auth_service.hash_one_time_token(verification_token)
        user.verification_token_expires = datetime.now(timezone.utc) + timedelta(
            hours=settings.EMAIL_VERIFICATION_TOKEN_EXPIRE_HOURS
        )

        # Send email
        email_sent = await email_service.send_verification_email(
            user_email,
            username,
            verification_token
        )
        if email_sent:
            await db.commit()
        else:
            await db.rollback()
            logger.error("Verification email could not be sent for %s; token update rolled back", user_email)

    # Always return success to prevent user enumeration
    return MessageResponse(
        message="If the email exists and is not verified, a verification link has been sent.",
        success=True
    )


@router.post("/contact-developer", response_model=MessageResponse)
async def contact_developer(
    payload: DeveloperContactRequest,
    request: Request,
    _rate_limit=Depends(RateLimitPresets.strict),
):
    if not settings.DEVELOPER_CONTACT_EMAIL:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Developer contact is not configured",
        )

    from app.services.email_service import email_service

    forwarded = request.headers.get("x-forwarded-for", "")
    requester_ip = forwarded.split(",")[0].strip() if forwarded else (request.client.host if request.client else "unknown")
    user_agent = request.headers.get("user-agent", "unknown")

    safe_name = escape(payload.name)
    safe_email = escape(str(payload.email))
    safe_message_html = escape(payload.message).replace("\n", "<br/>")
    safe_message_text = payload.message.strip()

    subject = f"{settings.APP_NAME} | Let's connect from {payload.name}"
    html_content = (
        "<h3>New developer contact request</h3>"
        f"<p><strong>Name:</strong> {safe_name}</p>"
        f"<p><strong>Email:</strong> {safe_email}</p>"
        f"<p><strong>Message:</strong><br/>{safe_message_html}</p>"
        "<hr/>"
        f"<p><strong>Requester IP:</strong> {escape(requester_ip)}</p>"
        f"<p><strong>User-Agent:</strong> {escape(user_agent)}</p>"
    )
    text_content = (
        "New developer contact request\n"
        f"Name: {payload.name}\n"
        f"Email: {payload.email}\n"
        f"Message:\n{safe_message_text}\n\n"
        f"Requester IP: {requester_ip}\n"
        f"User-Agent: {user_agent}"
    )

    sent = await email_service.send_email(
        to_email=settings.DEVELOPER_CONTACT_EMAIL,
        subject=subject,
        html_content=html_content,
        text_content=text_content,
    )
    if not sent:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Unable to deliver message right now",
        )

    return MessageResponse(message="Message sent to developer.", success=True)


@router.post("/login", response_model=LoginResponse)
async def login(
    login_data: UserLogin,
    request: Request,
    response: Response,
    db: AsyncSession = Depends(get_db),
    _rate_limit=Depends(RateLimitPresets.strict)
):
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
        refresh_token=refresh_token  # Returned in body for two-hop frontends (e.g. Streamlit)
    )


@router.post("/refresh", response_model=TokenResponse)
async def refresh_token(
    response: Response,
    request: Request,
    token_data: TokenRefresh = None,
    db: AsyncSession = Depends(get_db)
):
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

    # Use server-side configured expiry (never trust client-provided values)
    cookie_max_age = settings.REFRESH_TOKEN_EXPIRE_DAYS * 24 * 60 * 60

    # Update refresh token in cookie
    response.set_cookie(
        key="refresh_token",
        value=new_refresh_token,
        max_age=cookie_max_age,
        httponly=True,
        secure=settings.ENVIRONMENT == "production",
        samesite="lax",
        path="/"
    )

    return TokenResponse(
        access_token=new_access_token,
        token_type="bearer",
        expires_in=settings.ACCESS_TOKEN_EXPIRE_HOURS * 3600,
        refresh_token=new_refresh_token  # Returned in body for two-hop frontends
    )


@router.post("/logout", response_model=MessageResponse)
async def logout(
    response: Response,
    request: Request,
    user_id: str = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
    _rate_limit=Depends(RateLimitPresets.strict)
):
    # Get refresh token from cookie
    refresh_token = request.cookies.get("refresh_token")

    if refresh_token:
        try:
            # Decode token to get session
            payload = jwt_manager.decode_token(refresh_token)
            session_id = payload.get("sid")

            if session_id:
                # Revoke only this session for device-level logout
                await db.execute(
                    update(UserSession)
                    .where(
                        and_(
                            UserSession.session_id == session_id,
                            UserSession.user_id == user_id,
                            UserSession.is_active == True
                        )
                    )
                    .values(
                        is_active=False,
                        revoked_at=datetime.now(timezone.utc)
                    )
                )
                await db.commit()
        except Exception as e:
            logger.warning(f"Error revoking session: {e}")

    _clear_refresh_cookie(response)

    return MessageResponse(
        message="Logged out successfully",
        success=True
    )


@router.post("/logout-all", response_model=MessageResponse)
async def logout_all(
    response: Response,
    user_id: str = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
    _rate_limit=Depends(RateLimitPresets.strict),
):
    await db.execute(
        update(UserSession)
        .where(
            and_(
                UserSession.user_id == user_id,
                UserSession.is_active == True
            )
        )
        .values(
            is_active=False,
            revoked_at=datetime.now(timezone.utc)
        )
    )
    await db.commit()

    # Also clear cookie in current client
    _clear_refresh_cookie(response)

    return MessageResponse(
        message="Logged out from all devices successfully",
        success=True
    )


@router.post("/password-reset-request", response_model=MessageResponse)
async def request_password_reset(
    data: PasswordResetRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
    _rate_limit=Depends(RateLimitPresets.strict)
):
    await auth_service.request_password_reset(data.email, db)

    return MessageResponse(
        message="If the email exists, a password reset link has been sent.",
        success=True
    )


@router.post("/password-reset", response_model=MessageResponse)
async def reset_password(
    data: PasswordReset,
    request: Request,
    db: AsyncSession = Depends(get_db),
    _rate_limit=Depends(RateLimitPresets.strict)
):
    await auth_service.reset_password(data.token, data.new_password, db)

    return MessageResponse(
        message="Password reset successfully. Please log in with your new password.",
        success=True
    )


@router.post("/change-password", response_model=MessageResponse)
async def change_password(
    data: PasswordChange,
    user_id: str = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db)
):
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


@router.get("/me", response_model=UserDetailResponse)
async def get_current_user(
    user_id: str = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db)
):
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


@router.get("/sessions", response_model=List[SessionResponse])
async def get_user_sessions(
    user_id: str = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db)
):
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
