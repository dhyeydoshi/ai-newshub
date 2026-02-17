from __future__ import annotations

import logging
from typing import Optional
from urllib.parse import quote

import streamlit as st
import streamlit.components.v1 as components

from frontend_config import config

logger = logging.getLogger(__name__)

_COOKIE_NAME = config.SESSION_COOKIE_NAME  # default: "streamlit_session"
_COOKIE_MAX_AGE = config.SESSION_MAX_AGE   # default: 3600 (seconds)


def get_browser_cookie(name: str = _COOKIE_NAME) -> Optional[str]:

    try:
        value = st.context.cookies.get(name)
        return value if value else None
    except Exception:
        # Graceful fallback for older Streamlit or unexpected errors
        return None


def set_browser_cookie(
    value: str,
    name: str = _COOKIE_NAME,
    max_age: int = _COOKIE_MAX_AGE,
    path: str = "/",
    secure: bool = False,
    samesite: str = "Lax",
) -> None:
    
    safe_value = quote(value, safe="")
    parts = [
        f"{name}={safe_value}",
        f"path={path}",
        f"max-age={max_age}",
        f"SameSite={samesite}",
    ]
    if secure:
        parts.append("Secure")

    cookie_str = "; ".join(parts)

    components.html(
        f'<script>document.cookie="{cookie_str}";</script>',
        height=0,
        width=0,
    )


def delete_browser_cookie(
    name: str = _COOKIE_NAME,
    path: str = "/",
) -> None:
    """Remove a browser cookie by setting max-age=0."""
    components.html(
        f'<script>document.cookie="{name}=; path={path}; max-age=0";</script>',
        height=0,
        width=0,
    )
