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

    def trigger_news_fetch(
        self,
        queries: Optional[List[str]] = None,
        sources: Optional[List[str]] = None,
        limit: int = 50
    ) -> Dict[str, Any]:
        """Manually trigger news fetch (requires authentication)"""
        try:
            params = {"limit": limit}
            if queries:
                params["queries"] = queries
            if sources:
                params["sources"] = sources

            response = self.session.post(
                f"{self.base_url}/news/fetch-now",
                params=params,
                headers=self._get_headers(),
            )
            return self._handle_response(response)
        except Exception as exc:
            return {"success": False, "error": str(exc)}

    def get_task_status(self, task_id: str) -> Dict[str, Any]:
        """Get Celery task status."""
        try:
            response = self.session.get(
                f"{self.base_url}/news/task-status/{task_id}",
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

    def create_api_key(
        self,
        name: str,
        scopes: Optional[List[str]] = None,
        expires_in_days: int = 30,
    ) -> Dict[str, Any]:
        """Create a new integration API key."""
        payload: Dict[str, Any] = {
            "name": name,
            "scopes": scopes or ["feed:read"],
            "expires_in_days": expires_in_days,
        }
        try:
            response = self.session.post(
                f"{self.base_url}/integrations/api-keys",
                json=payload,
                headers=self._get_headers(),
            )
            return self._handle_response(response)
        except Exception as exc:
            return {"success": False, "error": str(exc)}

    def list_api_keys(self) -> Dict[str, Any]:
        """List integration API keys."""
        try:
            response = self.session.get(
                f"{self.base_url}/integrations/api-keys",
                headers=self._get_headers(),
            )
            return self._handle_response(response)
        except Exception as exc:
            return {"success": False, "error": str(exc)}

    def revoke_api_key(self, key_id: str) -> Dict[str, Any]:
        """Revoke an integration API key."""
        try:
            response = self.session.delete(
                f"{self.base_url}/integrations/api-keys/{key_id}",
                headers=self._get_headers(),
            )
            return self._handle_response(response)
        except Exception as exc:
            return {"success": False, "error": str(exc)}

    def rotate_api_key(self, key_id: str) -> Dict[str, Any]:
        """Rotate an integration API key."""
        try:
            response = self.session.post(
                f"{self.base_url}/integrations/api-keys/{key_id}/rotate",
                headers=self._get_headers(),
            )
            return self._handle_response(response)
        except Exception as exc:
            return {"success": False, "error": str(exc)}

    def create_feed(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """Create custom integration feed."""
        try:
            response = self.session.post(
                f"{self.base_url}/integrations/feeds",
                json=data,
                headers=self._get_headers(),
            )
            return self._handle_response(response)
        except Exception as exc:
            return {"success": False, "error": str(exc)}

    def list_feeds(self) -> Dict[str, Any]:
        """List custom integration feeds."""
        try:
            response = self.session.get(
                f"{self.base_url}/integrations/feeds",
                headers=self._get_headers(),
            )
            return self._handle_response(response)
        except Exception as exc:
            return {"success": False, "error": str(exc)}

    def get_feed(self, feed_id: str) -> Dict[str, Any]:
        """Get custom feed details."""
        try:
            response = self.session.get(
                f"{self.base_url}/integrations/feeds/{feed_id}",
                headers=self._get_headers(),
            )
            return self._handle_response(response)
        except Exception as exc:
            return {"success": False, "error": str(exc)}

    def update_feed(self, feed_id: str, data: Dict[str, Any]) -> Dict[str, Any]:
        """Update custom feed."""
        try:
            response = self.session.put(
                f"{self.base_url}/integrations/feeds/{feed_id}",
                json=data,
                headers=self._get_headers(),
            )
            return self._handle_response(response)
        except Exception as exc:
            return {"success": False, "error": str(exc)}

    def delete_feed(self, feed_id: str) -> Dict[str, Any]:
        """Deactivate custom feed."""
        try:
            response = self.session.delete(
                f"{self.base_url}/integrations/feeds/{feed_id}",
                headers=self._get_headers(),
            )
            return self._handle_response(response)
        except Exception as exc:
            return {"success": False, "error": str(exc)}

    def create_bundle(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """Create feed bundle."""
        try:
            response = self.session.post(
                f"{self.base_url}/integrations/bundles",
                json=data,
                headers=self._get_headers(),
            )
            return self._handle_response(response)
        except Exception as exc:
            return {"success": False, "error": str(exc)}

    def list_bundles(self) -> Dict[str, Any]:
        """List feed bundles."""
        try:
            response = self.session.get(
                f"{self.base_url}/integrations/bundles",
                headers=self._get_headers(),
            )
            return self._handle_response(response)
        except Exception as exc:
            return {"success": False, "error": str(exc)}

    def get_bundle(self, bundle_id: str) -> Dict[str, Any]:
        """Get bundle details."""
        try:
            response = self.session.get(
                f"{self.base_url}/integrations/bundles/{bundle_id}",
                headers=self._get_headers(),
            )
            return self._handle_response(response)
        except Exception as exc:
            return {"success": False, "error": str(exc)}

    def update_bundle(self, bundle_id: str, data: Dict[str, Any]) -> Dict[str, Any]:
        """Update bundle metadata."""
        try:
            response = self.session.patch(
                f"{self.base_url}/integrations/bundles/{bundle_id}",
                json=data,
                headers=self._get_headers(),
            )
            return self._handle_response(response)
        except Exception as exc:
            return {"success": False, "error": str(exc)}

    def delete_bundle(self, bundle_id: str) -> Dict[str, Any]:
        """Deactivate bundle."""
        try:
            response = self.session.delete(
                f"{self.base_url}/integrations/bundles/{bundle_id}",
                headers=self._get_headers(),
            )
            return self._handle_response(response)
        except Exception as exc:
            return {"success": False, "error": str(exc)}

    def add_feed_to_bundle(self, bundle_id: str, feed_id: str) -> Dict[str, Any]:
        """Add feed to an existing bundle."""
        try:
            response = self.session.put(
                f"{self.base_url}/integrations/bundles/{bundle_id}/feeds/{feed_id}",
                headers=self._get_headers(),
            )
            return self._handle_response(response)
        except Exception as exc:
            return {"success": False, "error": str(exc)}

    def remove_feed_from_bundle(self, bundle_id: str, feed_id: str) -> Dict[str, Any]:
        """Remove feed from a bundle."""
        try:
            response = self.session.delete(
                f"{self.base_url}/integrations/bundles/{bundle_id}/feeds/{feed_id}",
                headers=self._get_headers(),
            )
            return self._handle_response(response)
        except Exception as exc:
            return {"success": False, "error": str(exc)}

    def create_webhook(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """Create integration webhook."""
        try:
            response = self.session.post(
                f"{self.base_url}/integrations/webhooks",
                json=data,
                headers=self._get_headers(),
            )
            return self._handle_response(response)
        except Exception as exc:
            return {"success": False, "error": str(exc)}

    def list_webhooks(self) -> Dict[str, Any]:
        """List integration webhooks."""
        try:
            response = self.session.get(
                f"{self.base_url}/integrations/webhooks",
                headers=self._get_headers(),
            )
            return self._handle_response(response)
        except Exception as exc:
            return {"success": False, "error": str(exc)}

    def update_webhook(self, webhook_id: str, data: Dict[str, Any]) -> Dict[str, Any]:
        """Update webhook configuration."""
        try:
            response = self.session.patch(
                f"{self.base_url}/integrations/webhooks/{webhook_id}",
                json=data,
                headers=self._get_headers(),
            )
            return self._handle_response(response)
        except Exception as exc:
            return {"success": False, "error": str(exc)}

    def delete_webhook(self, webhook_id: str) -> Dict[str, Any]:
        """Deactivate webhook."""
        try:
            response = self.session.delete(
                f"{self.base_url}/integrations/webhooks/{webhook_id}",
                headers=self._get_headers(),
            )
            return self._handle_response(response)
        except Exception as exc:
            return {"success": False, "error": str(exc)}

    def test_webhook(self, webhook_id: str) -> Dict[str, Any]:
        """Trigger test delivery for webhook."""
        try:
            response = self.session.post(
                f"{self.base_url}/integrations/webhooks/{webhook_id}/test",
                headers=self._get_headers(),
            )
            return self._handle_response(response)
        except Exception as exc:
            return {"success": False, "error": str(exc)}

    def get_integration_stats(self) -> Dict[str, Any]:
        """Get integration subsystem usage metrics."""
        try:
            response = self.session.get(
                f"{self.base_url}/integrations/stats",
                headers=self._get_headers(),
            )
            return self._handle_response(response)
        except Exception as exc:
            return {"success": False, "error": str(exc)}


# Export singleton instance
api_service = APIService()
