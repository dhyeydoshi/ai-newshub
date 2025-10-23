"""
Authentication Utilities
Handles authentication state and token management
"""
import streamlit as st
from typing import Optional
from services.api_service import api_service


def init_auth_state():
    """Initialize authentication state"""
    if "is_authenticated" not in st.session_state:
        st.session_state.is_authenticated = False
        st.session_state.is_authenticated = False
        st.session_state.access_token = None
        st.session_state.user_id = None
        st.session_state.username = None

        # Attempt auto-login on first load
        from services.api_service import api_service
        api_service.auto_login()
    if "access_token" not in st.session_state:
        st.session_state.access_token = None
    if "refresh_token" not in st.session_state:
        st.session_state.refresh_token = None
    if "user_id" not in st.session_state:
        st.session_state.user_id = None
    if "username" not in st.session_state:
        st.session_state.username = None


def is_authenticated() -> bool:
    """Check if user is authenticated"""
    return st.session_state.get("is_authenticated", False)


def get_current_user() -> Optional[dict]:
    """Get current user info"""
    if is_authenticated():
        return {
            "user_id": st.session_state.get("user_id"),
            "username": st.session_state.get("username")
        }
    return None


def require_auth(func):
    """Decorator to require authentication"""
    def wrapper(*args, **kwargs):
        if not is_authenticated():
            st.warning("⚠️ Please login to access this page")
            st.stop()
        return func(*args, **kwargs)
    return wrapper


def logout():
    """Logout user"""
    api_service.logout()
    st.session_state.clear()
    st.rerun()

