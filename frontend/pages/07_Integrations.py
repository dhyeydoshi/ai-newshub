import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

import streamlit as st

# Add frontend root to Python path for direct page execution.
frontend_dir = Path(__file__).parent.parent
if str(frontend_dir) not in sys.path:
    sys.path.insert(0, str(frontend_dir))

from services.api_service import api_service
from utils.auth import init_auth_state, require_auth
from utils.ui_helpers import (
    apply_custom_css,
    init_page_config,
    show_error,
    show_loading,
    show_success,
    show_toast,
)


init_page_config("Integrations | News Summarizer", "")
apply_custom_css()
init_auth_state()


def _safe_list(value: Any) -> List[Dict[str, Any]]:
    if isinstance(value, list):
        return value
    return []


def _safe_dict(value: Any) -> Dict[str, Any]:
    if isinstance(value, dict):
        return value
    return {}


def _load_integrations_data() -> Dict[str, Any]:
    data: Dict[str, Any] = {
        "api_keys": [],
        "feeds": [],
        "bundles": [],
        "webhooks": [],
        "stats": {},
        "errors": [],
    }

    calls = [
        ("api_keys", api_service.list_api_keys),
        ("feeds", api_service.list_feeds),
        ("bundles", api_service.list_bundles),
        ("webhooks", api_service.list_webhooks),
        ("stats", api_service.get_integration_stats),
    ]

    for name, fn in calls:
        result = fn()
        if not result.get("success"):
            data["errors"].append(f"{name}: {result.get('error', 'request failed')}")
            continue
        payload = result.get("data")
        if name == "api_keys":
            data["api_keys"] = _safe_dict(payload).get("keys", [])
        elif name == "feeds":
            data["feeds"] = _safe_dict(payload).get("feeds", [])
        elif name == "bundles":
            data["bundles"] = _safe_dict(payload).get("bundles", [])
        elif name == "webhooks":
            data["webhooks"] = _safe_list(payload)
        elif name == "stats":
            data["stats"] = _safe_dict(payload)
    return data


def _show_api_keys(api_keys: List[Dict[str, Any]]) -> None:
    st.markdown("### API Keys")
    st.caption("Create and manage per-user integration keys.")

    with st.form("create_api_key_form", clear_on_submit=True):
        col1, col2 = st.columns([2, 1])
        with col1:
            key_name = st.text_input("Key name", value="default-key")
        with col2:
            expires_days = st.number_input("Expires in days", min_value=1, max_value=365, value=30)

        scopes_raw = st.text_input("Scopes (comma-separated)", value="feed:read")
        submitted = st.form_submit_button("Create API key", type="primary")
        if submitted:
            scopes = [s.strip() for s in scopes_raw.split(",") if s.strip()]
            result = api_service.create_api_key(name=key_name, scopes=scopes, expires_in_days=int(expires_days))
            if result.get("success"):
                created = _safe_dict(result.get("data"))
                st.session_state["integration_last_api_key"] = created.get("api_key")
                show_success("API key created.")
                st.rerun()
            else:
                show_error(result.get("error", "Failed to create API key"))

    plain_key = st.session_state.pop("integration_last_api_key", None)
    if plain_key:
        st.warning("Save this API key now. It is shown only once.")
        st.code(plain_key)

    if not api_keys:
        st.info("No API keys found.")
        return

    for key in api_keys:
        key_id = str(key.get("key_id", ""))
        key_name = key.get("name", "Unnamed")
        prefix = key.get("prefix", "")
        request_count = key.get("request_count", 0)
        is_active = key.get("is_active", False)

        col1, col2, col3, col4 = st.columns([3, 2, 2, 2])
        with col1:
            st.write(f"**{key_name}**")
            st.caption(f"Prefix: {prefix} | ID: {key_id}")
        with col2:
            st.metric("Requests", request_count)
        with col3:
            st.write("Status")
            st.write("Active" if is_active else "Inactive")
        with col4:
            if st.button("Rotate", key=f"rotate_key_{key_id}"):
                result = api_service.rotate_api_key(key_id)
                if result.get("success"):
                    created = _safe_dict(result.get("data"))
                    st.session_state["integration_last_api_key"] = created.get("api_key")
                    show_success("API key rotated.")
                    st.rerun()
                else:
                    show_error(result.get("error", "Failed to rotate API key"))
            if st.button("Revoke", key=f"revoke_key_{key_id}"):
                result = api_service.revoke_api_key(key_id)
                if result.get("success"):
                    show_toast("API key revoked")
                    st.rerun()
                else:
                    show_error(result.get("error", "Failed to revoke API key"))
        st.divider()


def _show_feeds(api_keys: List[Dict[str, Any]], feeds: List[Dict[str, Any]]) -> None:
    st.markdown("### Custom Feeds")
    st.caption("Create filtered feeds with JSON/RSS/Atom links.")

    active_keys = [k for k in api_keys if k.get("is_active")]
    if not active_keys:
        st.info("Create an active API key first.")
        return

    key_options = {f"{k.get('name')} ({k.get('prefix')})": str(k.get("key_id")) for k in active_keys}

    with st.form("create_feed_form", clear_on_submit=True):
        name = st.text_input("Feed name", value="My custom feed")
        description = st.text_area("Description", value="", height=80)

        col1, col2, col3 = st.columns(3)
        with col1:
            selected_key_label = st.selectbox("API key", list(key_options.keys()))
        with col2:
            output_format = st.selectbox("Format", ["json", "rss", "atom"])
        with col3:
            language = st.text_input("Language", value="en")

        topic_options = [
            "technology",
            "science",
            "business",
            "politics",
            "health",
            "sports",
            "entertainment",
            "world",
        ]
        category_options = ["technology", "science", "business", "politics", "health", "sports", "world"]

        topics = st.multiselect("Topics", topic_options)
        categories = st.multiselect("Categories", category_options)
        keywords_raw = st.text_input("Keywords (comma-separated)", value="")
        sources_raw = st.text_input("Sources (comma-separated)", value="")

        col4, col5, col6 = st.columns(3)
        with col4:
            limit = st.number_input("Item limit", min_value=1, max_value=100, value=20)
        with col5:
            max_age_days = st.number_input("Max age (days)", min_value=1, max_value=30, value=7)
        with col6:
            min_score = st.slider("Min score", min_value=0.0, max_value=1.0, value=0.0, step=0.05)

        exclude_read = st.checkbox("Exclude read articles", value=True)
        create_feed = st.form_submit_button("Create feed", type="primary")
        if create_feed:
            keywords = [k.strip() for k in keywords_raw.split(",") if k.strip()]
            sources = [s.strip() for s in sources_raw.split(",") if s.strip()]
            payload = {
                "name": name,
                "description": description or None,
                "api_key_id": key_options[selected_key_label],
                "format": output_format,
                "filters": {
                    "topics": topics,
                    "exclude_topics": [],
                    "categories": categories,
                    "keywords": keywords,
                    "exclude_keywords": [],
                    "sources": sources,
                    "exclude_sources": [],
                    "language": language.strip() or "en",
                    "exclude_read": exclude_read,
                    "min_score": float(min_score),
                    "max_age_days": int(max_age_days),
                    "limit": int(limit),
                    "sort_mode": "date",
                },
            }
            result = api_service.create_feed(payload)
            if result.get("success"):
                show_success("Feed created.")
                st.rerun()
            else:
                show_error(result.get("error", "Failed to create feed"))

    if not feeds:
        st.info("No feeds created yet.")
        return

    for feed in feeds:
        feed_id = str(feed.get("feed_id", ""))
        name = feed.get("name", "Unnamed feed")
        description = feed.get("description", "")
        filters = _safe_dict(feed.get("filters"))
        feed_url = feed.get("feed_url", "")
        rss_url = feed.get("rss_url", "")
        atom_url = feed.get("atom_url", "")

        st.write(f"**{name}**")
        if description:
            st.caption(description)
        st.caption(f"Topics: {', '.join(filters.get('topics', [])) or 'none'}")
        st.code(feed_url)
        st.code(rss_url)
        st.code(atom_url)

        if st.button("Delete Feed", key=f"delete_feed_{feed_id}"):
            result = api_service.delete_feed(feed_id)
            if result.get("success"):
                show_toast("Feed deactivated")
                st.rerun()
            else:
                show_error(result.get("error", "Failed to delete feed"))
        st.divider()


def _show_bundles(api_keys: List[Dict[str, Any]], feeds: List[Dict[str, Any]], bundles: List[Dict[str, Any]]) -> None:
    st.markdown("### Bundles")
    st.caption("Group multiple feeds into a single endpoint.")

    active_keys = [k for k in api_keys if k.get("is_active")]
    if not active_keys:
        st.info("Create an active API key first.")
        return
    if not feeds:
        st.info("Create at least one feed before creating bundles.")
        return

    key_options = {f"{k.get('name')} ({k.get('prefix')})": str(k.get("key_id")) for k in active_keys}
    feed_options = {f.get("name", "Unnamed"): str(f.get("feed_id")) for f in feeds if f.get("feed_id")}

    with st.form("create_bundle_form", clear_on_submit=True):
        name = st.text_input("Bundle name", value="My bundle")
        description = st.text_area("Bundle description", value="", height=80)
        selected_key = st.selectbox("API key", list(key_options.keys()), key="bundle_api_key")
        output_format = st.selectbox("Format", ["json", "rss", "atom"], key="bundle_format")
        selected_feed_names = st.multiselect("Feeds", list(feed_options.keys()))
        create_bundle = st.form_submit_button("Create bundle", type="primary")
        if create_bundle:
            selected_ids = [feed_options[fname] for fname in selected_feed_names]
            payload = {
                "name": name,
                "description": description or None,
                "api_key_id": key_options[selected_key],
                "format": output_format,
                "feed_ids": selected_ids,
            }
            result = api_service.create_bundle(payload)
            if result.get("success"):
                show_success("Bundle created.")
                st.rerun()
            else:
                show_error(result.get("error", "Failed to create bundle"))

    if not bundles:
        st.info("No bundles created yet.")
        return

    id_to_feed_name = {str(f.get("feed_id")): f.get("name", "Unnamed feed") for f in feeds}
    for bundle in bundles:
        bundle_id = str(bundle.get("bundle_id", ""))
        name = bundle.get("name", "Unnamed bundle")
        description = bundle.get("description", "")
        member_ids = [str(fid) for fid in bundle.get("feed_ids", [])]
        member_names = [id_to_feed_name.get(fid, fid) for fid in member_ids]
        st.write(f"**{name}**")
        if description:
            st.caption(description)
        st.caption(f"Feeds: {', '.join(member_names) if member_names else 'none'}")
        st.code(bundle.get("feed_url", ""))
        st.code(bundle.get("rss_url", ""))
        st.code(bundle.get("atom_url", ""))

        if st.button("Delete Bundle", key=f"delete_bundle_{bundle_id}"):
            result = api_service.delete_bundle(bundle_id)
            if result.get("success"):
                show_toast("Bundle deactivated")
                st.rerun()
            else:
                show_error(result.get("error", "Failed to delete bundle"))
        st.divider()


def _show_webhooks(feeds: List[Dict[str, Any]], bundles: List[Dict[str, Any]], webhooks: List[Dict[str, Any]]) -> None:
    st.markdown("### Webhooks")
    st.caption("Push feed updates to Slack, Discord, Telegram, Email, or generic webhook endpoints.")

    if not feeds and not bundles:
        st.info("Create at least one feed or bundle before creating webhooks.")
        return

    feed_options = {f.get("name", "Unnamed"): str(f.get("feed_id")) for f in feeds if f.get("feed_id")}
    bundle_options = {b.get("name", "Unnamed"): str(b.get("bundle_id")) for b in bundles if b.get("bundle_id")}

    with st.form("create_webhook_form", clear_on_submit=True):
        platform = st.selectbox("Platform", ["email", "slack", "discord", "telegram", "generic"])
        target = st.text_input("Target", value="", help="Email address or webhook URL, based on platform.")
        scope = st.radio("Attach to", ["Feed", "Bundle"], horizontal=True)
        batch_interval = st.number_input("Batch interval (minutes)", min_value=5, max_value=1440, value=30)
        max_failures = st.number_input("Max failures", min_value=1, max_value=20, value=5)

        selected_feed_id: Optional[str] = None
        selected_bundle_id: Optional[str] = None
        if scope == "Feed":
            if not feed_options:
                st.info("No feeds available.")
            else:
                selected_feed_name = st.selectbox("Feed", list(feed_options.keys()))
                selected_feed_id = feed_options[selected_feed_name]
        else:
            if not bundle_options:
                st.info("No bundles available.")
            else:
                selected_bundle_name = st.selectbox("Bundle", list(bundle_options.keys()))
                selected_bundle_id = bundle_options[selected_bundle_name]

        create_webhook = st.form_submit_button("Create webhook", type="primary")
        if create_webhook:
            payload: Dict[str, Any] = {
                "platform": platform,
                "target": target.strip(),
                "batch_interval_minutes": int(batch_interval),
                "max_failures": int(max_failures),
            }
            if selected_feed_id:
                payload["feed_id"] = selected_feed_id
            if selected_bundle_id:
                payload["bundle_id"] = selected_bundle_id

            result = api_service.create_webhook(payload)
            if result.get("success"):
                show_success("Webhook created.")
                st.rerun()
            else:
                show_error(result.get("error", "Failed to create webhook"))

    if not webhooks:
        st.info("No webhooks created yet.")
        return

    for webhook in webhooks:
        webhook_id = str(webhook.get("webhook_id", ""))
        st.write(f"**{webhook.get('platform', 'unknown').upper()}**")
        st.caption(
            f"Target: {webhook.get('target_preview', '')} | "
            f"Interval: {webhook.get('batch_interval_minutes', 0)}m | "
            f"Failures: {webhook.get('failure_count', 0)}/{webhook.get('max_failures', 0)}"
        )
        col1, col2 = st.columns(2)
        with col1:
            if st.button("Test", key=f"test_webhook_{webhook_id}"):
                result = api_service.test_webhook(webhook_id)
                if result.get("success"):
                    response = _safe_dict(result.get("data"))
                    ok = response.get("success", False)
                    if ok:
                        show_success("Webhook test succeeded.")
                    else:
                        show_error(response.get("message", "Webhook test failed"))
                else:
                    show_error(result.get("error", "Failed to test webhook"))
        with col2:
            if st.button("Delete", key=f"delete_webhook_{webhook_id}"):
                result = api_service.delete_webhook(webhook_id)
                if result.get("success"):
                    show_toast("Webhook deactivated")
                    st.rerun()
                else:
                    show_error(result.get("error", "Failed to delete webhook"))
        st.divider()


def _show_usage(stats: Dict[str, Any]) -> None:
    st.markdown("### Usage")
    st.caption("Current integration usage and limits.")

    if not stats:
        st.info("Usage data unavailable.")
        return

    col1, col2, col3, col4 = st.columns(4)
    with col1:
        st.metric("Active API Keys", stats.get("active_api_keys", 0))
    with col2:
        st.metric("Active Feeds", stats.get("active_feeds", 0))
    with col3:
        st.metric("Active Bundles", stats.get("active_bundles", 0))
    with col4:
        st.metric("Active Webhooks", stats.get("active_webhooks", 0))

    jobs = _safe_dict(stats.get("delivery_jobs"))
    col5, col6, col7 = st.columns(3)
    with col5:
        st.metric("Delivered Jobs", jobs.get("delivered", 0))
    with col6:
        st.metric("Queued Jobs", jobs.get("queued", 0))
    with col7:
        st.metric("Failed Jobs", jobs.get("failed_or_dead_letter", 0))

    limits = _safe_dict(stats.get("limits"))
    if limits:
        st.markdown("#### Limits")
        st.json(limits)


@require_auth
def main() -> None:
    st.title("Integrations")
    st.caption("Manage API keys, custom feeds, bundles, and webhooks.")

    if st.button("Refresh", use_container_width=False):
        st.rerun()

    with show_loading("Loading integration data..."):
        data = _load_integrations_data()

    errors = data.get("errors", [])
    for error in errors:
        show_error(f"Failed to load {error}")

    tabs = st.tabs(["API Keys", "Custom Feeds", "Bundles", "Webhooks", "Usage"])

    with tabs[0]:
        _show_api_keys(data.get("api_keys", []))
    with tabs[1]:
        _show_feeds(data.get("api_keys", []), data.get("feeds", []))
    with tabs[2]:
        _show_bundles(data.get("api_keys", []), data.get("feeds", []), data.get("bundles", []))
    with tabs[3]:
        _show_webhooks(data.get("feeds", []), data.get("bundles", []), data.get("webhooks", []))
    with tabs[4]:
        _show_usage(data.get("stats", {}))


if __name__ == "__main__":
    main()
