import os
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

    # Security
    SECRET_KEY: str = os.getenv("SECRET_KEY", "default-secret-key-change-in-production")
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

    # Debug
    DEBUG: bool = os.getenv("DEBUG", "false").lower() == "true"

    # Page Configuration
    PAGE_TITLE: str = "News Summarizer"
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
