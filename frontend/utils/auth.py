from typing import Optional
import streamlit as st
from services.api_service import api_service


def init_auth_state() -> None:
    """Initialize authentication state"""
    if "is_authenticated" not in st.session_state:
        st.session_state.is_authenticated = False
        st.session_state.access_token = None
        st.session_state.refresh_token = None
        st.session_state.user_id = None
        st.session_state.username = None

        # Attempt auto-login on first load
        api_service.auto_login()

    st.session_state.setdefault("access_token", None)
    st.session_state.setdefault("refresh_token", None)
    st.session_state.setdefault("user_id", None)
    st.session_state.setdefault("username", None)


def is_authenticated() -> bool:
    """Check if user is authenticated"""
    return st.session_state.get("is_authenticated", False)


def get_current_user() -> Optional[dict]:
    """Get current user info"""
    if is_authenticated():
        return {
            "user_id": st.session_state.get("user_id"),
            "username": st.session_state.get("username"),
        }
    return None


def require_auth(func):
    """Decorator to require authentication"""
    def wrapper(*args, **kwargs):
        if not is_authenticated():
            st.warning("Please login to access this page")
            st.stop()
        return func(*args, **kwargs)

    return wrapper


def logout(all_devices: bool = False) -> None:
    """Logout user and redirect to home page."""
    result = api_service.logout(all_devices=all_devices)
    warning_message = None

    if all_devices and not result.get("success", False):
        warning_message = result.get("error", "Failed to revoke all sessions on the server.")

    st.session_state.clear()
    if warning_message:
        st.session_state["auth_notice"] = warning_message

    st.switch_page("Home.py")
