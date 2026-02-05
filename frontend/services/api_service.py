"""API Service Layer
Handles all communication with the backend API
"""
from typing import Optional, Dict, Any, List
import logging
import requests
import streamlit as st
from frontend_config import config

logger = logging.getLogger(__name__)


class APIService:
    """Service for making API calls"""

    def __init__(self) -> None:
        self.base_url = config.API_ENDPOINT
        self.session = requests.Session()

    def _get_token(self) -> Optional[str]:
        """Get JWT token from session state"""
        return st.session_state.get("access_token")

    def _get_headers(self, include_auth: bool = True) -> Dict[str, str]:
        """Get request headers"""
        headers = config.get_headers()
        if include_auth:
            token = self._get_token()
            if token:
                headers["Authorization"] = f"Bearer {token}"
        return headers

    def _handle_response(self, response: requests.Response) -> Dict[str, Any]:
        """Handle API response"""
        try:
            response.raise_for_status()
            try:
                return {"success": True, "data": response.json()}
            except ValueError:
                return {"success": True, "data": {"raw": response.text}}
        except requests.exceptions.HTTPError as exc:
            if response.status_code == 401:
                # Token expired - clear session
                self._clear_auth()
                st.rerun()
            logger.error("HTTP Error: %s", exc)
            try:
                error_data = response.json()
                return {"success": False, "error": error_data.get("error", str(exc))}
            except ValueError:
                return {"success": False, "error": str(exc)}
        except Exception as exc:
            logger.error("Request Error: %s", exc)
            return {"success": False, "error": str(exc)}

    def _clear_auth(self) -> None:
        """Clear authentication data"""
        for key in ["access_token", "refresh_token", "user_id", "username", "is_authenticated"]:
            if key in st.session_state:
                del st.session_state[key]

    # ======================================================================
    # AUTHENTICATION
    # ======================================================================

    def register(self, email: str, password: str, username: str, full_name: str) -> Dict[str, Any]:
        """Register new user"""
        try:
            response = self.session.post(
                f"{self.base_url}/auth/register",
                json={
                    "email": email,
                    "password": password,
                    "username": username,
                    "full_name": full_name,
                },
                headers=self._get_headers(include_auth=False),
            )
            return self._handle_response(response)
        except Exception as exc:
            return {"success": False, "error": str(exc)}

    def login(self, email: str, password: str, remember_me: bool = False) -> Dict[str, Any]:
        """Login user"""
        try:
            response = self.session.post(
                f"{self.base_url}/auth/login",
                json={"email": email, "password": password, "remember_me": remember_me},
                headers=self._get_headers(include_auth=False),
            )
            result = self._handle_response(response)

            if result["success"]:
                data = result["data"]
                st.session_state.access_token = data.get("access_token")
                st.session_state.refresh_token = data.get("refresh_token")
                st.session_state.user_id = data.get("user", {}).get("user_id")
                st.session_state.username = data.get("user", {}).get("username")
                st.session_state.is_authenticated = True

            return result
        except Exception as exc:
            return {"success": False, "error": str(exc)}

    def logout(self, all_devices: bool = False) -> Dict[str, Any]:
        """Logout user from current device or all devices."""
        endpoint = "/auth/logout-all" if all_devices else "/auth/logout"
        try:
            response = self.session.post(
                f"{self.base_url}{endpoint}",
                headers=self._get_headers(include_auth=all_devices),
            )

            if response.ok:
                try:
                    data = response.json()
                except ValueError:
                    data = {"raw": response.text}
                return {"success": True, "data": data}

            # Current-device logout is idempotent. Even if backend rejects
            # due token state, local auth should still be cleared.
            if not all_devices and response.status_code in (401, 403):
                return {"success": True, "data": {"message": "Logged out locally"}}

            try:
                error_data = response.json()
                error_msg = error_data.get("detail") or error_data.get("error") or response.text
            except ValueError:
                error_msg = response.text
            return {"success": False, "error": error_msg}
        except Exception as exc:
            if not all_devices:
                return {"success": True, "data": {"message": "Logged out locally"}}
            return {"success": False, "error": str(exc)}
        finally:
            self._clear_auth()
            self.session.cookies.clear()

    def refresh_token(self) -> Dict[str, Any]:
        """Refresh access token"""
        try:
            response = self.session.post(
                f"{self.base_url}/auth/refresh",
                headers=self._get_headers(include_auth=False),
            )
            result = self._handle_response(response)

            if result["success"]:
                data = result["data"]
                st.session_state.access_token = data.get("access_token")
                st.session_state.is_authenticated = True

            return result
        except Exception as exc:
            return {"success": False, "error": str(exc)}

    def auto_login(self) -> bool:
        """Attempt auto-login using persistent cookie"""
        try:
            if not self.session.cookies.get("refresh_token"):
                return False

            result = self.refresh_token()
            if result["success"]:
                st.session_state.is_authenticated = True

                profile_result = self.get_profile()
                if profile_result["success"]:
                    user = profile_result["data"]
                    st.session_state.user_id = user.get("user_id")
                    st.session_state.username = user.get("username")

                return True

            self.session.cookies.clear()
            return False
        except Exception as exc:
            logger.error("Auto-login failed: %s", exc)
            self.session.cookies.clear()
            return False

    # ======================================================================
    # NEWS
    # ======================================================================

    def get_latest_news(
        self, page: int = 1, limit: int = 10, topics: Optional[List[str]] = None
    ) -> Dict[str, Any]:
        """Get latest news articles from database"""
        try:
            params = {"page": page, "page_size": limit}
            if topics:
                params["topics"] = topics

            response = self.session.get(
                f"{self.base_url}/news/articles",
                params=params,
                headers=self._get_headers(),
            )
            return self._handle_response(response)
        except Exception as exc:
            return {"success": False, "error": str(exc)}

    def get_article(self, article_id: str) -> Dict[str, Any]:
        """Get article details"""
        try:
            response = self.session.get(
                f"{self.base_url}/news/article/{article_id}",
                headers=self._get_headers(),
            )
            return self._handle_response(response)
        except Exception as exc:
            return {"success": False, "error": str(exc)}

    def search_news(self, query: str, page: int = 1, limit: int = 10) -> Dict[str, Any]:
        """Search news articles"""
        try:
            response = self.session.get(
                f"{self.base_url}/news/search",
                params={"query": query, "page": page, "page_size": limit},
                headers=self._get_headers(),
            )
            return self._handle_response(response)
        except Exception as exc:
            return {"success": False, "error": str(exc)}

    def summarize_article(self, article_id: str, summary_length: str = "medium") -> Dict[str, Any]:
        """Get article summary"""
        try:
            response = self.session.get(
                f"{self.base_url}/news/summary/{article_id}",
                headers=self._get_headers(),
            )
            return self._handle_response(response)
        except Exception as exc:
            return {"success": False, "error": str(exc)}

    def trigger_news_fetch(self, queries: Optional[List[str]] = None, limit: int = 50) -> Dict[str, Any]:
        """Manually trigger news fetch (requires authentication)"""
        try:
            params = {"limit": limit}
            if queries:
                params["queries"] = queries

            response = self.session.post(
                f"{self.base_url}/news/fetch-now",
                params=params,
                headers=self._get_headers(),
            )
            return self._handle_response(response)
        except Exception as exc:
            return {"success": False, "error": str(exc)}

    def get_scheduler_status(self) -> Dict[str, Any]:
        """Get news scheduler status"""
        try:
            response = self.session.get(
                f"{self.base_url}/news/scheduler/status",
                headers=self._get_headers(),
            )
            return self._handle_response(response)
        except Exception as exc:
            return {"success": False, "error": str(exc)}

    # ======================================================================
    # RECOMMENDATIONS
    # ======================================================================

    def get_recommendations(self, limit: int = 10) -> Dict[str, Any]:
        """Get personalized recommendations"""
        try:
            response = self.session.get(
                f"{self.base_url}/recommendations",
                params={"limit": limit},
                headers=self._get_headers(),
            )
            return self._handle_response(response)
        except Exception as exc:
            return {"success": False, "error": str(exc)}

    def submit_feedback(
        self, article_id: str, feedback_type: str, time_spent_seconds: Optional[int] = None
    ) -> Dict[str, Any]:
        """Submit article feedback"""
        try:
            payload: Dict[str, Any] = {
                "article_id": article_id,
                "feedback_type": feedback_type,
            }
            if time_spent_seconds:
                payload["engagement_metrics"] = {"time_spent_seconds": time_spent_seconds}

            response = self.session.post(
                f"{self.base_url}/feedback/article",
                json=payload,
                headers=self._get_headers(),
            )
            return self._handle_response(response)
        except Exception as exc:
            return {"success": False, "error": str(exc)}

    # ======================================================================
    # USER
    # ======================================================================

    def get_profile(self) -> Dict[str, Any]:
        """Get user profile"""
        try:
            response = self.session.get(
                f"{self.base_url}/user/profile",
                headers=self._get_headers(),
            )
            return self._handle_response(response)
        except Exception as exc:
            return {"success": False, "error": str(exc)}

    def update_profile(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """Update user profile"""
        try:
            response = self.session.put(
                f"{self.base_url}/user/profile",
                json=data,
                headers=self._get_headers(),
            )
            return self._handle_response(response)
        except Exception as exc:
            return {"success": False, "error": str(exc)}

    def get_preferences(self) -> Dict[str, Any]:
        """Get user preferences"""
        try:
            response = self.session.get(
                f"{self.base_url}/user/preferences",
                headers=self._get_headers(),
            )
            return self._handle_response(response)
        except Exception as exc:
            return {"success": False, "error": str(exc)}

    def update_preferences(self, preferences: Dict[str, Any]) -> Dict[str, Any]:
        """Update user preferences"""
        try:
            response = self.session.put(
                f"{self.base_url}/user/preferences",
                json=preferences,
                headers=self._get_headers(),
            )
            return self._handle_response(response)
        except Exception as exc:
            return {"success": False, "error": str(exc)}

    def get_reading_history(self, limit: int = 50) -> Dict[str, Any]:
        """Get reading history"""
        try:
            response = self.session.get(
                f"{self.base_url}/user/reading-history",
                params={"page": 1, "page_size": limit},
                headers=self._get_headers(),
            )
            return self._handle_response(response)
        except Exception as exc:
            return {"success": False, "error": str(exc)}


# Export singleton instance
api_service = APIService()
