from typing import Optional, Dict, Any, List
import logging
import requests
import streamlit as st
from frontend_config import config

logger = logging.getLogger(__name__)


class APIService:
    """Service for making API calls to the backend."""

    _REQUEST_TIMEOUT = (5, 30)  # (connect, read) seconds

    def __init__(self) -> None:
        self.base_url = config.API_ENDPOINT

    @staticmethod
    def _get_session() -> requests.Session:
        """Return a per-Streamlit-user requests.Session.

        Stored in st.session_state so each browser session gets its own
        cookie jar, preventing cross-user token leakage.
        """
        if "_http_session" not in st.session_state:
            st.session_state["_http_session"] = requests.Session()
        return st.session_state["_http_session"]

    # ── internal helpers ──────────────────────────────────────────────

    def _get_token(self) -> Optional[str]:
        return st.session_state.get("access_token")

    def _get_headers(self, include_auth: bool = True) -> Dict[str, str]:
        headers = config.get_headers()
        if include_auth:
            token = self._get_token()
            if token:
                headers["Authorization"] = f"Bearer {token}"
        return headers

    def _handle_response(
        self,
        response: requests.Response,
        *,
        logout_on_401: bool = True,
    ) -> Dict[str, Any]:
        try:
            response.raise_for_status()
            try:
                return {"success": True, "data": response.json()}
            except ValueError:
                return {"success": True, "data": {"raw": response.text}}
        except requests.exceptions.HTTPError as exc:
            if response.status_code == 401 and logout_on_401:
                self._clear_auth()
                st.rerun()
            logger.error("HTTP Error: %s", exc)
            try:
                error_data = response.json()
                error_message = (
                    error_data.get("error")
                    or error_data.get("detail")
                    or str(exc)
                )
                return {"success": False, "error": error_message}
            except ValueError:
                return {"success": False, "error": str(exc)}
        except Exception as exc:
            logger.error("Request Error: %s", exc)
            return {"success": False, "error": str(exc)}

    def _clear_auth(self) -> None:
        for key in [
            "access_token",
            "refresh_token",
            "user_id",
            "username",
            "is_authenticated",
            "integration_api_key_vault",
            "integration_last_api_key",
        ]:
            st.session_state.pop(key, None)

    def _request(
        self,
        method: str,
        path: str,
        *,
        json: Any = None,
        params: Optional[Dict[str, Any]] = None,
        include_auth: bool = True,
    ) -> Dict[str, Any]:
        """Generic request helper that wraps every API call."""
        try:
            response = self._get_session().request(
                method,
                f"{self.base_url}{path}",
                json=json,
                params=params,
                headers=self._get_headers(include_auth=include_auth),
                timeout=self._REQUEST_TIMEOUT,
            )
            return self._handle_response(response, logout_on_401=include_auth)
        except Exception as exc:
            return {"success": False, "error": str(exc)}

    # ── auth ──────────────────────────────────────────────────────────

    def register(self, email: str, password: str, username: str, full_name: str) -> Dict[str, Any]:
        return self._request(
            "POST", "/auth/register", include_auth=False,
            json={"email": email, "password": password, "username": username, "full_name": full_name},
        )

    def contact_developer(self, name: str, email: str, message: str) -> Dict[str, Any]:
        return self._request(
            "POST",
            "/auth/contact-developer",
            include_auth=False,
            json={"name": name, "email": email, "message": message},
        )

    def verify_email(self, token: str) -> Dict[str, Any]:
        return self._request(
            "POST",
            "/auth/verify-email",
            include_auth=False,
            json={"token": token},
        )

    def resend_verification(self, email: str) -> Dict[str, Any]:
        return self._request(
            "POST",
            "/auth/resend-verification",
            include_auth=False,
            json={"email": email},
        )

    def request_password_reset(self, email: str) -> Dict[str, Any]:
        return self._request(
            "POST",
            "/auth/password-reset-request",
            include_auth=False,
            json={"email": email},
        )

    def reset_password(self, token: str, new_password: str) -> Dict[str, Any]:
        return self._request(
            "POST",
            "/auth/password-reset",
            include_auth=False,
            json={"token": token, "new_password": new_password},
        )

    def login(self, email: str, password: str, remember_me: bool = False) -> Dict[str, Any]:
        result = self._request(
            "POST", "/auth/login", include_auth=False,
            json={"email": email, "password": password, "remember_me": remember_me},
        )
        if result["success"]:
            data = result["data"]
            st.session_state.access_token = data.get("access_token")
            st.session_state.refresh_token = data.get("refresh_token")
            st.session_state.user_id = data.get("user", {}).get("user_id")
            st.session_state.username = data.get("user", {}).get("username")
            st.session_state.is_authenticated = True
        return result

    def logout(self, all_devices: bool = False) -> Dict[str, Any]:
        endpoint = "/auth/logout-all" if all_devices else "/auth/logout"
        try:
            response = self._get_session().post(
                f"{self.base_url}{endpoint}",
                headers=self._get_headers(include_auth=True),
                timeout=self._REQUEST_TIMEOUT,
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
            self._get_session().cookies.clear()

    def refresh_token(self) -> Dict[str, Any]:
        result = self._request("POST", "/auth/refresh", include_auth=False)
        if result["success"]:
            st.session_state.access_token = result["data"].get("access_token")
            st.session_state.is_authenticated = True
        return result

    def auto_login(self) -> bool:
        try:
            if not self._get_session().cookies.get("refresh_token"):
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
            self._get_session().cookies.clear()
            return False
        except Exception as exc:
            logger.error("Auto-login failed: %s", exc)
            self._get_session().cookies.clear()
            return False

    # ── news ──────────────────────────────────────────────────────────

    def get_latest_news(
        self, page: int = 1, limit: int = 10, topics: Optional[List[str]] = None,
        language: Optional[str] = None,
    ) -> Dict[str, Any]:
        params: Dict[str, Any] = {"page": page, "page_size": limit}
        if topics:
            params["topics"] = topics
        if language:
            params["language"] = language
        return self._request("GET", "/news/articles", params=params)

    def get_article(self, article_id: str) -> Dict[str, Any]:
        return self._request("GET", f"/news/article/{article_id}")

    def search_news(
        self,
        query: str,
        page: int = 1,
        limit: int = 10,
        topics: Optional[List[str]] = None,
        sources: Optional[List[str]] = None,
        from_date: Optional[str] = None,
        to_date: Optional[str] = None,
        sort_by: str = "relevance",
    ) -> Dict[str, Any]:
        params: Dict[str, Any] = {
            "query": query,
            "page": page,
            "page_size": limit,
            "sort_by": sort_by,
        }
        if topics:
            params["topics"] = topics
        if sources:
            params["sources"] = sources
        if from_date:
            params["from_date"] = from_date
        if to_date:
            params["to_date"] = to_date
        return self._request("GET", "/news/search", params=params)

    def trigger_news_fetch(
        self,
        queries: Optional[List[str]] = None,
        sources: Optional[List[str]] = None,
        limit: int = 50,
    ) -> Dict[str, Any]:
        params: Dict[str, Any] = {"limit": limit}
        if queries:
            params["queries"] = queries
        if sources:
            params["sources"] = sources
        return self._request("POST", "/news/fetch-now", params=params)

    def get_task_status(self, task_id: str) -> Dict[str, Any]:
        return self._request("GET", f"/news/task-status/{task_id}")

    # ── recommendations & feedback ────────────────────────────────────

    def get_recommendations(self, limit: int = 10) -> Dict[str, Any]:
        return self._request("GET", "/recommendations", params={"limit": limit})

    def submit_feedback(
        self, article_id: str, feedback_type: str, time_spent_seconds: Optional[int] = None,
    ) -> Dict[str, Any]:
        payload: Dict[str, Any] = {"article_id": article_id, "feedback_type": feedback_type}
        if time_spent_seconds:
            payload["engagement_metrics"] = {"time_spent_seconds": time_spent_seconds}
        return self._request("POST", "/feedback/article", json=payload)

    # ── user ──────────────────────────────────────────────────────────

    def get_profile(self) -> Dict[str, Any]:
        return self._request("GET", "/user/profile")

    def update_profile(self, data: Dict[str, Any]) -> Dict[str, Any]:
        return self._request("PUT", "/user/profile", json=data)

    def get_preferences(self) -> Dict[str, Any]:
        return self._request("GET", "/user/preferences")

    def update_preferences(self, preferences: Dict[str, Any]) -> Dict[str, Any]:
        return self._request("PUT", "/user/preferences", json=preferences)

    def get_reading_history(self, limit: int = 50) -> Dict[str, Any]:
        return self._request("GET", "/user/reading-history", params={"page": 1, "page_size": limit})

    # ── integration: api keys ─────────────────────────────────────────

    def create_api_key(
        self, name: str, scopes: Optional[List[str]] = None, expires_in_days: int = 30,
    ) -> Dict[str, Any]:
        return self._request("POST", "/integrations/api-keys", json={
            "name": name, "scopes": scopes or ["feed:read"], "expires_in_days": expires_in_days,
        })

    def list_api_keys(self) -> Dict[str, Any]:
        return self._request("GET", "/integrations/api-keys")

    def revoke_api_key(self, key_id: str) -> Dict[str, Any]:
        return self._request("DELETE", f"/integrations/api-keys/{key_id}")

    def delete_api_key(self, key_id: str) -> Dict[str, Any]:
        return self._request("DELETE", f"/integrations/api-keys/{key_id}/permanent")

    def rotate_api_key(self, key_id: str) -> Dict[str, Any]:
        return self._request("POST", f"/integrations/api-keys/{key_id}/rotate")

    # ── integration: feeds ────────────────────────────────────────────

    def create_feed(self, data: Dict[str, Any]) -> Dict[str, Any]:
        return self._request("POST", "/integrations/feeds", json=data)

    def list_feeds(self) -> Dict[str, Any]:
        return self._request("GET", "/integrations/feeds")

    def get_feed(self, feed_id: str) -> Dict[str, Any]:
        return self._request("GET", f"/integrations/feeds/{feed_id}")

    def update_feed(self, feed_id: str, data: Dict[str, Any]) -> Dict[str, Any]:
        return self._request("PUT", f"/integrations/feeds/{feed_id}", json=data)

    def delete_feed(self, feed_id: str) -> Dict[str, Any]:
        return self._request("DELETE", f"/integrations/feeds/{feed_id}")

    # ── integration: bundles ──────────────────────────────────────────

    def create_bundle(self, data: Dict[str, Any]) -> Dict[str, Any]:
        return self._request("POST", "/integrations/bundles", json=data)

    def list_bundles(self) -> Dict[str, Any]:
        return self._request("GET", "/integrations/bundles")

    def get_bundle(self, bundle_id: str) -> Dict[str, Any]:
        return self._request("GET", f"/integrations/bundles/{bundle_id}")

    def update_bundle(self, bundle_id: str, data: Dict[str, Any]) -> Dict[str, Any]:
        return self._request("PATCH", f"/integrations/bundles/{bundle_id}", json=data)

    def delete_bundle(self, bundle_id: str) -> Dict[str, Any]:
        return self._request("DELETE", f"/integrations/bundles/{bundle_id}")

    def add_feed_to_bundle(self, bundle_id: str, feed_id: str) -> Dict[str, Any]:
        return self._request("PUT", f"/integrations/bundles/{bundle_id}/feeds/{feed_id}")

    def remove_feed_from_bundle(self, bundle_id: str, feed_id: str) -> Dict[str, Any]:
        return self._request("DELETE", f"/integrations/bundles/{bundle_id}/feeds/{feed_id}")

    # ── integration: webhooks ─────────────────────────────────────────

    def create_webhook(self, data: Dict[str, Any]) -> Dict[str, Any]:
        return self._request("POST", "/integrations/webhooks", json=data)

    def list_webhooks(self) -> Dict[str, Any]:
        return self._request("GET", "/integrations/webhooks")

    def update_webhook(self, webhook_id: str, data: Dict[str, Any]) -> Dict[str, Any]:
        return self._request("PATCH", f"/integrations/webhooks/{webhook_id}", json=data)

    def delete_webhook(self, webhook_id: str) -> Dict[str, Any]:
        return self._request("DELETE", f"/integrations/webhooks/{webhook_id}")

    def test_webhook(self, webhook_id: str) -> Dict[str, Any]:
        return self._request("POST", f"/integrations/webhooks/{webhook_id}/test")

    def get_integration_stats(self) -> Dict[str, Any]:
        return self._request("GET", "/integrations/stats")


# Export singleton instance
api_service = APIService()
