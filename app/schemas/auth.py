from datetime import datetime
from typing import Optional, List
from pydantic import BaseModel, EmailStr, Field, field_validator
from uuid import UUID
import re


class UserRegister(BaseModel):
    """User registration request"""
    email: EmailStr
    username: str = Field(..., min_length=3, max_length=50)
    password: str = Field(..., min_length=8, max_length=100)
    full_name: Optional[str] = Field(None, max_length=255)
    data_processing_consent: bool = Field(default=False)

    @field_validator("username")
    @classmethod
    def validate_username(cls, v: str) -> str:
        """Validate username format"""
        if not re.match(r"^[a-zA-Z0-9_-]+$", v):
            raise ValueError("Username can only contain letters, numbers, underscores, and hyphens")
        return v

    @field_validator("password")
    @classmethod
    def validate_password(cls, v: str) -> str:
        """Basic password validation (detailed validation in service)"""
        if len(v) < 8:
            raise ValueError("Password must be at least 8 characters long")
        return v


class UserLogin(BaseModel):
    """User login request"""
    email: EmailStr
    password: str
    remember_me: bool = Field(default=False)


class TokenRefresh(BaseModel):
    """Token refresh request"""
    refresh_token: Optional[str] = None  # Can be from cookie or body


class PasswordResetRequest(BaseModel):
    """Password reset request"""
    email: EmailStr


class PasswordReset(BaseModel):
    """Password reset with token"""
    token: str
    new_password: str = Field(..., min_length=8, max_length=100)

    @field_validator("new_password")
    @classmethod
    def validate_password(cls, v: str) -> str:
        if len(v) < 8:
            raise ValueError("Password must be at least 8 characters long")
        return v


class PasswordChange(BaseModel):
    """Password change for authenticated users"""
    current_password: str
    new_password: str = Field(..., min_length=8, max_length=100)

    @field_validator("new_password")
    @classmethod
    def validate_password(cls, v: str) -> str:
        if len(v) < 8:
            raise ValueError("Password must be at least 8 characters long")
        return v


class EmailVerification(BaseModel):
    """Email verification request"""
    token: str


class ResendVerification(BaseModel):
    """Resend verification email"""
    email: EmailStr


class UserResponse(BaseModel):
    """User response"""
    user_id: UUID
    email: EmailStr
    username: str
    full_name: Optional[str] = None
    is_verified: bool
    is_active: bool
    created_at: datetime
    last_login_at: Optional[datetime] = None

    model_config = {"from_attributes": True}


class TokenResponse(BaseModel):
    """Token response"""
    access_token: str
    token_type: str = "bearer"
    expires_in: int  # seconds
    refresh_token: Optional[str] = None  # Only if not in httpOnly cookie


class LoginResponse(BaseModel):
    """Login response with user info and tokens"""
    user: UserResponse
    access_token: str
    token_type: str = "bearer"
    expires_in: int
    refresh_token: Optional[str] = None


class MessageResponse(BaseModel):
    """Generic message response"""
    message: str
    success: bool = True


class PasswordStrengthResponse(BaseModel):
    """Password strength validation response"""
    valid: bool
    score: int
    feedback: str
    suggestions: List[str]
    crack_time: Optional[str] = None


class SessionResponse(BaseModel):
    """User session response"""
    session_id: UUID
    device_info: Optional[str] = None
    ip_address: Optional[str] = None
    created_at: datetime
    last_used_at: datetime
    expires_at: datetime
    is_active: bool

    model_config = {"from_attributes": True}


class UserDetailResponse(UserResponse):
    """Detailed user response with additional info"""
    email_verified_at: Optional[datetime] = None
    last_password_change: Optional[datetime] = None
    active_sessions: int = 0
