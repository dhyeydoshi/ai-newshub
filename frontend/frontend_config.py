import os
import secrets
import warnings
from typing import Optional

from dotenv import load_dotenv

# Load environment variables
load_dotenv()


class Config:
    """Application configuration"""

    # API Configuration
    API_BASE_URL: str = os.getenv("API_BASE_URL", "http://localhost:8000")
    API_VERSION: str = os.getenv("API_VERSION", "v1")
    API_ENDPOINT: str = f"{API_BASE_URL}/api/{API_VERSION}"
    ENVIRONMENT: str = os.getenv("ENVIRONMENT", "development").strip().lower()
    DEBUG: bool = os.getenv("DEBUG", "false").lower() == "true"

    # Security
    _provided_secret: str = os.getenv("SECRET_KEY", "").strip()
    if _provided_secret:
        SECRET_KEY: str = _provided_secret
    elif ENVIRONMENT == "production":
        raise RuntimeError("SECRET_KEY must be set in production for frontend security")
    else:
        SECRET_KEY: str = secrets.token_urlsafe(32)
        warnings.warn(
            "Frontend SECRET_KEY is not set; generated ephemeral key for this process. "
            "Set SECRET_KEY explicitly before production deployment.",
            UserWarning,
        )

    SESSION_COOKIE_NAME: str = os.getenv("SESSION_COOKIE_NAME", "streamlit_session")
    SESSION_MAX_AGE: int = int(os.getenv("SESSION_MAX_AGE", "3600"))

    # Features
    ENABLE_ANALYTICS: bool = os.getenv("ENABLE_ANALYTICS", "true").lower() == "true"
    ENABLE_INTEGRATIONS: bool = os.getenv(
        "ENABLE_INTEGRATIONS",
        os.getenv("ENABLE_INTEGRATION_API", "false"),
    ).lower() == "true"
    ARTICLES_PER_PAGE: int = int(os.getenv("ARTICLES_PER_PAGE", "10"))
    CACHE_TTL: int = int(os.getenv("CACHE_TTL", "300"))

    # Sidebar developer contact
    DEVELOPER_CONTACT_EMAIL: str = os.getenv("DEVELOPER_CONTACT_EMAIL", "").strip()
    DEVELOPER_CONTACT_URL: str = os.getenv("DEVELOPER_CONTACT_URL", "").strip()
    DEVELOPER_GITHUB_URL: str = os.getenv("DEVELOPER_GITHUB_URL", "").strip()
    DEVELOPER_LINKEDIN_URL: str = os.getenv("DEVELOPER_LINKEDIN_URL", "").strip()
    DEVELOPER_TWITTER_URL: str = os.getenv("DEVELOPER_TWITTER_URL", "").strip()

    # Page Configuration
    PAGE_TITLE: str = "News Central"
    PAGE_ICON: str = ""
    LAYOUT: str = "wide"

    @classmethod
    def get_headers(cls, token: Optional[str] = None) -> dict:
        """Get API request headers"""
        headers = {
            "Content-Type": "application/json",
            "Accept": "application/json",
        }
        if token:
            headers["Authorization"] = f"Bearer {token}"
        return headers


# Export singleton instance
config = Config()
