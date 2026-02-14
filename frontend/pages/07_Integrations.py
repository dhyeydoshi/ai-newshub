from typing import Any, Dict, List, Optional

import streamlit as st

from services.api_service import api_service
from frontend_config import config
from utils.auth import init_auth_state, require_auth, logout
from utils.ui_helpers import (
    apply_custom_css,
    init_page_config,
    show_error,
    show_loading,
    show_success,
    show_toast,
)


init_page_config("Integrations | News Central", "")
apply_custom_css()
init_auth_state()

SUPPORTED_INTEGRATION_SCOPES: List[Dict[str, str]] = [
    {
        "scope": "feed:read",
        "description": "Required to read public feed/bundle endpoints under /api/v1/integration/*",
    },
    {
        "scope": "*",
        "description": "Wildcard access to all scopes (use cautiously)",
    },
]


def _safe_list(value: Any) -> List[Dict[str, Any]]:
    if isinstance(value, list):
        return value
    return []


def _safe_dict(value: Any) -> Dict[str, Any]:
    if isinstance(value, dict):
        return value
    return {}


def _get_api_key_vault() -> Dict[str, str]:
    vault = st.session_state.setdefault("integration_api_key_vault", {})
    if not isinstance(vault, dict):
        vault = {}
        st.session_state["integration_api_key_vault"] = vault
    return vault


def _remember_plain_api_key(payload: Dict[str, Any]) -> None:
    key_id = str(payload.get("key_id") or payload.get("api_key_id") or "").strip()
    plain_key = str(payload.get("api_key") or "").strip()
    if key_id and plain_key:
        vault = _get_api_key_vault()
        vault[key_id] = plain_key


def _forget_plain_api_key(key_id: str) -> None:
    vault = _get_api_key_vault()
    vault.pop(str(key_id), None)


def _mask_api_key(plain_key: Optional[str], prefix: str) -> str:
    key = str(plain_key or "").strip()
    if key:
        if len(key) <= 16:
            return f"{key[:4]}...{key[-2:]}"
        return f"{key[:10]}...{key[-6:]}"
    prefix_clean = str(prefix or "").strip()
    return f"{prefix_clean}..." if prefix_clean else "Unavailable"


def _load_integrations_data() -> Dict[str, Any]:
    data: Dict[str, Any] = {
        "api_keys": [],
        "feeds": [],
        "bundles": [],
        "webhooks": [],
        "stats": {},
        "errors": [],
        "disabled": False,
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
            error_message = str(result.get("error", "request failed"))
            if "integration api is disabled" in error_message.lower():
                data["disabled"] = True
                break
            data["errors"].append(f"{name}: {error_message}")
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
    st.markdown("### :material/key: API Keys")
    st.caption("Create and manage per-user integration keys.")
    with st.expander(":material/shield: Supported integration scopes", expanded=True):
        st.table(
            [
                {"Scope": row["scope"], "Description": row["description"]}
                for row in SUPPORTED_INTEGRATION_SCOPES
            ]
        )

    with st.form("create_api_key_form", clear_on_submit=True):
        col1, col2 = st.columns([2, 1])
        with col1:
            key_name = st.text_input("Key name", value="default-key")
        with col2:
            expires_days = st.number_input("Expires in days", min_value=1, max_value=365, value=30)

        scope_defaults = ["feed:read"]
        selected_scopes = st.multiselect(
            "Scopes",
            options=[row["scope"] for row in SUPPORTED_INTEGRATION_SCOPES],
            default=scope_defaults,
            help="Select supported scopes for this key.",
        )
        scopes_raw = st.text_input(
            "Additional scopes (optional, comma-separated)",
            value="",
            help="Use only if backend supports extra custom scopes.",
        )
        submitted = st.form_submit_button("Create API key", type="primary")
        if submitted:
            custom_scopes = [s.strip() for s in scopes_raw.split(",") if s.strip()]
            scopes = list(dict.fromkeys([*selected_scopes, *custom_scopes])) or ["feed:read"]
            result = api_service.create_api_key(name=key_name, scopes=scopes, expires_in_days=int(expires_days))
            if result.get("success"):
                created = _safe_dict(result.get("data"))
                _remember_plain_api_key(created)
                st.session_state["integration_last_api_key"] = created.get("api_key")
                show_success("API key created.")
                st.rerun()
            else:
                show_error(result.get("error", "Failed to create API key"))

    plain_key = st.session_state.get("integration_last_api_key")
    if plain_key:
        st.warning("Latest generated API key (available only in this browser session).")
        st.code(plain_key)

    if not api_keys:
        st.info(":material/info: No API keys found. Create one above to get started.")
        return

    vault = _get_api_key_vault()

    for idx, key in enumerate(api_keys):
        key_id = str(key.get("key_id") or key.get("api_key_id") or "")
        uid = key_id or str(idx)
        key_name = key.get("name", "Unnamed")
        prefix = key.get("prefix") or key.get("key_prefix") or ""
        request_count = key.get("request_count", 0)
        is_active = key.get("is_active", False)
        created_at = key.get("created_at", "")

        col1, col2, col3, col4 = st.columns([3, 2, 2, 2])
        with col1:
            st.write(f"**{key_name}**")
            if created_at:
                from utils.ui_helpers import format_date
 
                st.caption(f"Created {format_date(created_at)}")
            with st.expander("Show details"):
                st.caption(f"**Prefix:** `{prefix}`")
                st.caption(f"**ID:** `{key_id}`")
                scopes = key.get("scopes") or ["feed:read"]
                st.caption(f"**Scopes:** `{', '.join(scopes)}`")
                cached_full_key = vault.get(key_id)
                st.caption(f"**API Key (partial):** `{_mask_api_key(cached_full_key, prefix)}`")
                if cached_full_key:
                    st.caption("Full API key is available in this browser session for copy.")
                    st.code(cached_full_key)
                else:
                    st.info("Full API key is not recoverable from backend. Rotate to generate a new copyable key.")
        with col2:
            st.metric("Requests", request_count)
        with col3:
            st.write("Status")
            if is_active:
                st.badge("Active", color="green")
            else:
                st.badge("Inactive", color="red")
        with col4:
            if is_active:
                if st.button(":material/autorenew: Rotate", key=f"rotate_key_{uid}"):
                    result = api_service.rotate_api_key(key_id)
                    if result.get("success"):
                        created = _safe_dict(result.get("data"))
                        _remember_plain_api_key(created)
                        st.session_state["integration_last_api_key"] = created.get("api_key")
                        show_success("API key rotated.")
                        st.rerun()
                    else:
                        show_error(result.get("error", "Failed to rotate API key"))
                if st.button(":material/block: Revoke", key=f"revoke_key_{uid}"):
                    result = api_service.revoke_api_key(key_id)
                    if result.get("success"):
                        _forget_plain_api_key(key_id)
                        show_toast("API key revoked")
                        st.rerun()
                    else:
                        show_error(result.get("error", "Failed to revoke API key"))
            else:
                if st.button(":material/delete: Delete", key=f"delete_key_{uid}", type="primary"):
                    result = api_service.delete_api_key(key_id)
                    if result.get("success"):
                        _forget_plain_api_key(key_id)
                        show_toast("API key deleted")
                        st.rerun()
                    else:
                        show_error(result.get("error", "Failed to delete API key"))
        st.divider()


def _show_feeds(api_keys: List[Dict[str, Any]], feeds: List[Dict[str, Any]]) -> None:
    st.markdown("### :material/rss_feed: Custom Feeds")
    st.caption("Create filtered feeds with JSON/RSS/Atom links.")

    active_keys = [k for k in api_keys if k.get("is_active")]
    if not active_keys:
        st.info(":material/key: Create an active API key first.")
        return

    key_options = {
        f"{k.get('name')} ({k.get('prefix') or k.get('key_prefix') or 'no-prefix'})": 
        str(k.get("key_id") or k.get("api_key_id") or "")
        for k in active_keys
    }

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
        st.info(":material/inbox: No feeds created yet. Use the form above to create one.")
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

        if st.button(":material/delete: Delete Feed", key=f"delete_feed_{feed_id}"):
            result = api_service.delete_feed(feed_id)
            if result.get("success"):
                show_toast("Feed deactivated")
                st.rerun()
            else:
                show_error(result.get("error", "Failed to delete feed"))
        st.divider()


def _show_bundles(api_keys: List[Dict[str, Any]], feeds: List[Dict[str, Any]], bundles: List[Dict[str, Any]]) -> None:
    st.markdown("### :material/folder_special: Bundles")
    st.caption("Group multiple feeds into a single endpoint.")

    active_keys = [k for k in api_keys if k.get("is_active")]
    if not active_keys:
        st.info(":material/key: Create an active API key first.")
        return
    if not feeds:
        st.info(":material/rss_feed: Create at least one feed before creating bundles.")
        return

    key_options = {
        f"{k.get('name')} ({k.get('prefix') or k.get('key_prefix') or 'no-prefix'})": 
        str(k.get("key_id") or k.get("api_key_id") or "")
        for k in active_keys
    }
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
        st.info(":material/inbox: No bundles created yet. Use the form above to create one.")
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

        if st.button(":material/delete: Delete Bundle", key=f"delete_bundle_{bundle_id}"):
            result = api_service.delete_bundle(bundle_id)
            if result.get("success"):
                show_toast("Bundle deactivated")
                st.rerun()
            else:
                show_error(result.get("error", "Failed to delete bundle"))
        st.divider()


def _show_webhooks(feeds: List[Dict[str, Any]], bundles: List[Dict[str, Any]], webhooks: List[Dict[str, Any]]) -> None:
    st.markdown("### :material/webhook: Webhooks")
    st.caption("Push feed updates to Slack, Discord, Telegram, Email, or generic webhook endpoints.")

    if not feeds and not bundles:
        st.info(":material/rss_feed: Create at least one feed or bundle before creating webhooks.")
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
        st.info(":material/inbox: No webhooks created yet. Use the form above to create one.")
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
            if st.button(":material/send: Test", key=f"test_webhook_{webhook_id}"):
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
            if st.button(":material/delete: Delete", key=f"delete_webhook_{webhook_id}"):
                result = api_service.delete_webhook(webhook_id)
                if result.get("success"):
                    show_toast("Webhook deactivated")
                    st.rerun()
                else:
                    show_error(result.get("error", "Failed to delete webhook"))
        st.divider()


def _show_usage(stats: Dict[str, Any]) -> None:
    st.markdown("### :material/bar_chart: Usage")
    st.caption("Current integration usage and limits.")

    if not stats:
        st.info(":material/info: Usage data unavailable.")
        return

    st.markdown("#### :material/check_circle: Active Resources")
    col1, col2 = st.columns(2)
    with col1:
        st.metric("Active API Keys", stats.get("active_api_keys", 0))
        st.metric("Active Feeds", stats.get("active_feeds", 0))
    with col2:
        st.metric("Active Bundles", stats.get("active_bundles", 0))
        st.metric("Active Webhooks", stats.get("active_webhooks", 0))

    jobs = _safe_dict(stats.get("delivery_jobs"))
    st.markdown("#### :material/local_shipping: Delivery Jobs")
    col3, col4, col5 = st.columns(3)
    with col3:
        st.metric("Delivered", jobs.get("delivered", 0))
    with col4:
        st.metric("Queued", jobs.get("queued", 0))
    with col5:
        st.metric("Failed/Dead Letter", jobs.get("failed_or_dead_letter", 0))

    limits = _safe_dict(stats.get("limits"))
    if limits:
        st.markdown("#### :material/speed: Limits")
        label_map = {
            "max_api_keys_per_user": "Max API Keys per User",
            "max_feeds_per_user": "Max Feeds per User",
            "max_bundles_per_user": "Max Bundles per User",
            "max_feeds_per_bundle": "Max Feeds per Bundle",
            "max_webhooks_per_user": "Max Webhooks per User",
            "min_batch_interval_minutes": "Min Batch Interval (Minutes)",
            "max_items_per_batch": "Max Items per Batch",
        }

        rows: List[Dict[str, Any]] = []
        for key in label_map:
            if key in limits:
                rows.append({"Limit": label_map[key], "Value": limits.get(key)})

        # Render unknown keys too, if backend adds new limits in future.
        for key, value in limits.items():
            if key not in label_map:
                rows.append({"Limit": key.replace("_", " ").title(), "Value": value})

        if rows:
            st.table(rows)


def _show_documentation() -> None:
    st.markdown("### :material/menu_book: Integration Documentation")
    st.caption("Complete reference for API keys, feeds, bundles, and webhooks.")

    base_url = config.API_ENDPOINT

    # ── Quick Start ──────────────────────────────────────────────────
    with st.expander(":material/rocket_launch: Quick Start Guide", expanded=True):
        st.markdown(f"""
**Getting started in 4 steps:**

1. **Create an API Key** — Go to the *API Keys* tab and create a key with the `feed:read` scope.
   Copy the key immediately; it is shown only once.

2. **Create a Custom Feed** — Go to *Custom Feeds*, select your API key, pick topics/filters,
   and choose an output format (JSON, RSS, or Atom).

3. **Consume the Feed** — Use the generated feed URL with your API key to pull articles:
   ```
   curl -H "Authorization: Bearer YOUR_API_KEY" \\
        "{base_url.replace('/api/v1', '')}/api/v1/integration/feeds/your-feed-slug"
   ```

4. **(Optional) Set Up Webhooks** — Attach a webhook to your feed or bundle to receive
   automatic push notifications on Slack, Discord, Telegram, Email, or a custom URL.
""")

    # ── Authentication ───────────────────────────────────────────────
    with st.expander(":material/lock: Authentication"):
        st.markdown("""
This integration system uses **two separate authentication methods**:

| Context | Auth Method | Used For |
|---------|-------------|----------|
| **Management API** | JWT Bearer Token (login session) | Creating/managing keys, feeds, bundles, webhooks |
| **Public Feed API** | Integration API Key | Consuming feed/bundle data programmatically |

**Three ways to pass your Integration API Key** (checked in this order):

1. **Authorization header** (recommended):
   ```
   Authorization: Bearer nk_abc123...
   ```

2. **Custom header**:
   ```
   X-Integration-Key: nk_abc123...
   ```

3. **Query parameter** (use only when headers aren't possible):
   ```
   ?token=nk_abc123...
   ```
""")

    # ── API Keys ─────────────────────────────────────────────────────
    with st.expander(":material/key: API Keys Reference"):
        st.markdown(f"""
API keys authenticate requests to the **public feed/bundle endpoints**.

**Endpoints:**

| Method | Path | Description |
|--------|------|-------------|
| `POST` | `{base_url}/integrations/api-keys` | Create a new API key |
| `GET` | `{base_url}/integrations/api-keys` | List all your API keys |
| `POST` | `{base_url}/integrations/api-keys/{{key_id}}/rotate` | Rotate a key (revoke old, issue new) |
| `DELETE` | `{base_url}/integrations/api-keys/{{key_id}}` | Revoke a key (soft delete) |
| `DELETE` | `{base_url}/integrations/api-keys/{{key_id}}/permanent` | Permanently delete a revoked key |

**Create Key — Request Body:**
```json
{{
  "name": "my-production-key",
  "scopes": ["feed:read"],
  "expires_in_days": 90
}}
```

**Create Key — Response:**
```json
{{
  "api_key": "nk_a1b2c3d4e5f6...",
  "key_id": "550e8400-e29b-41d4-a716-446655440000",
  "prefix": "nk_a1b2c3",
  "name": "my-production-key",
  "scopes": ["feed:read"],
  "expires_at": "2026-05-14T00:00:00Z",
  "message": "API key created. Save it now because it will not be shown again."
}}
```

**Available Scopes:**

| Scope | Description |
|-------|-------------|
| `feed:read` | Read access to feed and bundle endpoints |
| `*` | Wildcard — full access to all scopes |

**Key Properties:**
- Keys are **hashed** server-side (SHA-256) — the plain key is only returned at creation/rotation time
- Each key has an independent **hourly rate limit** (default: 1,000 requests/hour)
- Usage counters track total requests per key
""")

    # ── Feeds ────────────────────────────────────────────────────────
    with st.expander(":material/rss_feed: Custom Feeds Reference"):
        st.markdown(f"""
Custom feeds let you define filtered article streams accessible via a permanent URL.

**Management Endpoints:**

| Method | Path | Description |
|--------|------|-------------|
| `POST` | `{base_url}/integrations/feeds` | Create a feed |
| `GET` | `{base_url}/integrations/feeds` | List your feeds |
| `GET` | `{base_url}/integrations/feeds/{{feed_id}}` | Get feed details |
| `PUT` | `{base_url}/integrations/feeds/{{feed_id}}` | Update a feed |
| `DELETE` | `{base_url}/integrations/feeds/{{feed_id}}` | Deactivate a feed |

**Public Consumption Endpoints** (use API key):

| Path | Format |
|------|--------|
| `/api/v1/integration/feeds/{{slug}}` | Feed's default format |
| `/api/v1/integration/feeds/{{slug}}/rss` | RSS XML |
| `/api/v1/integration/feeds/{{slug}}/atom` | Atom XML |

**Query Parameters for public endpoints:**

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `limit` | int | 20 | Items per page (1–100) |
| `since` | datetime | — | Only articles published after this time |
| `sort` | string | `date` | `date` or `relevance` |

**Create Feed — Example Request:**
```json
{{
  "name": "AI & Tech News",
  "description": "Latest articles on AI and technology",
  "api_key_id": "550e8400-e29b-41d4-a716-446655440000",
  "format": "json",
  "filters": {{
    "topics": ["technology", "science"],
    "categories": ["technology"],
    "keywords": ["artificial intelligence", "machine learning"],
    "exclude_keywords": ["crypto"],
    "language": "en",
    "exclude_read": true,
    "min_score": 0.1,
    "max_age_days": 7,
    "limit": 20,
    "sort_mode": "date"
  }}
}}
```

**Consume Feed — Example:**
```bash
# JSON (default)
curl -H "Authorization: Bearer nk_abc123..." \\
     "{base_url.replace('/api/v1', '')}/api/v1/integration/feeds/ai-tech-news"

# RSS
curl -H "Authorization: Bearer nk_abc123..." \\
     "{base_url.replace('/api/v1', '')}/api/v1/integration/feeds/ai-tech-news/rss"

# Atom
curl -H "Authorization: Bearer nk_abc123..." \\
     "{base_url.replace('/api/v1', '')}/api/v1/integration/feeds/ai-tech-news/atom"
```

**JSON Response Example:**
```json
{{
  "feed_id": "...",
  "name": "AI & Tech News",
  "generated_at": "2026-02-14T10:30:00Z",
  "total": 15,
  "items": [
    {{
      "article_id": "...",
      "title": "OpenAI Announces New Model",
      "url": "https://example.com/article",
      "source_name": "TechCrunch",
      "author": "Jane Doe",
      "excerpt": "OpenAI has released...",
      "image_url": "https://example.com/image.jpg",
      "topics": ["technology", "artificial intelligence"],
      "category": "technology",
      "published_date": "2026-02-14T08:00:00Z",
      "relevance_score": 0.92
    }}
  ],
  "next_cursor": "..."
}}
```
""")

    # ── Feed Filters Reference ───────────────────────────────────────
    with st.expander(":material/filter_alt: Feed Filters — Complete Reference"):
        st.table([
            {"Field": "topics", "Type": "list[str]", "Default": "[]", "Description": "Include only articles matching these topics"},
            {"Field": "exclude_topics", "Type": "list[str]", "Default": "[]", "Description": "Exclude articles with these topics"},
            {"Field": "categories", "Type": "list[str]", "Default": "[]", "Description": "Include only articles in these categories"},
            {"Field": "keywords", "Type": "list[str]", "Default": "[]", "Description": "Include articles containing these keywords"},
            {"Field": "exclude_keywords", "Type": "list[str]", "Default": "[]", "Description": "Exclude articles containing these keywords"},
            {"Field": "sources", "Type": "list[str]", "Default": "[]", "Description": "Include only articles from these sources"},
            {"Field": "exclude_sources", "Type": "list[str]", "Default": "[]", "Description": "Exclude articles from these sources"},
            {"Field": "language", "Type": "str", "Default": "en", "Description": "ISO language code (e.g., en, fr, de)"},
            {"Field": "exclude_read", "Type": "bool", "Default": "true", "Description": "Exclude articles you've already read"},
            {"Field": "min_score", "Type": "float", "Default": "0.0", "Description": "Minimum relevance score (0.0–1.0)"},
            {"Field": "max_age_days", "Type": "int", "Default": "7", "Description": "Maximum article age in days (1–30)"},
            {"Field": "limit", "Type": "int", "Default": "20", "Description": "Maximum items returned (1–100)"},
            {"Field": "sort_mode", "Type": "str", "Default": "date", "Description": "'date' (newest first) or 'relevance' (highest score first)"},
        ])
        st.info("All list fields are deduplicated, lowercased, HTML-escaped, and capped at 50 items max.")

    # ── Bundles ──────────────────────────────────────────────────────
    with st.expander(":material/folder_special: Bundles Reference"):
        st.markdown(f"""
Bundles group multiple custom feeds into a **single endpoint**, merging and deduplicating their results.

**Management Endpoints:**

| Method | Path | Description |
|--------|------|-------------|
| `POST` | `{base_url}/integrations/bundles` | Create a bundle |
| `GET` | `{base_url}/integrations/bundles` | List bundles |
| `GET` | `{base_url}/integrations/bundles/{{bundle_id}}` | Get bundle details |
| `PATCH` | `{base_url}/integrations/bundles/{{bundle_id}}` | Update bundle metadata |
| `PUT` | `{base_url}/integrations/bundles/{{bundle_id}}/feeds/{{feed_id}}` | Add a feed to the bundle |
| `DELETE` | `{base_url}/integrations/bundles/{{bundle_id}}/feeds/{{feed_id}}` | Remove a feed from the bundle |
| `DELETE` | `{base_url}/integrations/bundles/{{bundle_id}}` | Deactivate a bundle |

**Public Consumption:**

| Path | Format |
|------|--------|
| `/api/v1/integration/bundles/{{slug}}` | Bundle's default format |
| `/api/v1/integration/bundles/{{slug}}/rss` | RSS XML |
| `/api/v1/integration/bundles/{{slug}}/atom` | Atom XML |

**Create Bundle — Example:**
```json
{{
  "name": "All Tech Sources",
  "description": "Combined feed from all technology-related feeds",
  "api_key_id": "550e8400-e29b-41d4-a716-446655440000",
  "format": "rss",
  "feed_ids": [
    "feed-uuid-1",
    "feed-uuid-2"
  ]
}}
```

**Consume Bundle — Example:**
```bash
curl -H "Authorization: Bearer nk_abc123..." \\
     "{base_url.replace('/api/v1', '')}/api/v1/integration/bundles/all-tech-sources/rss"
```

**Behavior Notes:**
- When feeds overlap (same article in multiple member feeds), the bundle deduplicates by article ID
- The **highest relevance score** is kept when duplicates exist across member feeds
- A bundle can contain up to **10–20 feeds** depending on server configuration
""")

    # ── Webhooks ─────────────────────────────────────────────────────
    with st.expander(":material/webhook: Webhooks Reference"):
        st.markdown(f"""
Webhooks push article updates from your feeds or bundles to external platforms automatically.

**Management Endpoints:**

| Method | Path | Description |
|--------|------|-------------|
| `POST` | `{base_url}/integrations/webhooks` | Create a webhook |
| `GET` | `{base_url}/integrations/webhooks` | List webhooks |
| `PATCH` | `{base_url}/integrations/webhooks/{{webhook_id}}` | Update a webhook |
| `DELETE` | `{base_url}/integrations/webhooks/{{webhook_id}}` | Deactivate a webhook |
| `POST` | `{base_url}/integrations/webhooks/{{webhook_id}}/test` | Send a test delivery |

**Supported Platforms:**

| Platform | Target Format | Secret | Notes |
|----------|---------------|--------|-------|
| `slack` | Slack Incoming Webhook URL | Optional | HTTPS URL required |
| `discord` | Discord Webhook URL | Optional | HTTPS URL required |
| `telegram` | Chat ID (e.g., `-1001234567890`) | **Required** — Bot token | Format: `123456:ABC-DEF1234ghIkl-zyx` |
| `email` | Email address | Optional | Valid email format required |
| `generic` | Any HTTPS webhook URL | Optional | Signed with `X-Webhook-Signature` if secret provided |

**Create Webhook — Examples:**

*Slack:*
```json
{{
  "platform": "slack",
  "target": "https://hooks.slack.com/services/T00/B00/xxxx",
  "feed_id": "your-feed-uuid",
  "batch_interval_minutes": 60,
  "max_failures": 5
}}
```

*Discord:*
```json
{{
  "platform": "discord",
  "target": "https://discord.com/api/webhooks/123456/abcdef",
  "bundle_id": "your-bundle-uuid",
  "batch_interval_minutes": 30
}}
```

*Telegram:*
```json
{{
  "platform": "telegram",
  "target": "-1001234567890",
  "secret": "123456:ABC-DEF1234ghIkl-zyx",
  "feed_id": "your-feed-uuid",
  "batch_interval_minutes": 15
}}
```

*Email:*
```json
{{
  "platform": "email",
  "target": "user@example.com",
  "feed_id": "your-feed-uuid",
  "batch_interval_minutes": 120
}}
```

*Generic Webhook:*
```json
{{
  "platform": "generic",
  "target": "https://api.example.com/webhook",
  "secret": "my-signing-secret",
  "bundle_id": "your-bundle-uuid",
  "batch_interval_minutes": 30
}}
```
""")

    # ── Delivery Lifecycle ───────────────────────────────────────────
    with st.expander(":material/local_shipping: Webhook Delivery Lifecycle"):
        st.markdown("""
**How delivery works:**

1. **Batch Planning** — A background worker periodically checks each active webhook for new articles
   since its last successful delivery.

2. **Job Creation** — When new articles are found, a delivery job is created with status `pending`.

3. **Delivery Attempt** — The worker sends the batch payload to the target platform.

4. **On Success** — Job is marked `delivered`, the webhook's cursor advances, and the failure counter resets.

5. **On Failure** — Job is marked `retry_pending`, and retried with increasing backoff delays.

**Retry Backoff Schedule:**

| Attempt | Delay |
|---------|-------|
| 1st retry | 1 minute |
| 2nd retry | 5 minutes |
| 3rd retry | 15 minutes |
| 4th retry | 60 minutes |
| 5th retry | 240 minutes |

**Dead Letter:**
After reaching the `max_failures` threshold (default: 5), the webhook is **automatically deactivated**
and the job moves to `dead_letter` status. Re-enable the webhook manually after fixing the target issue.

**Job Statuses:**

| Status | Meaning |
|--------|---------|
| `pending` | Waiting for delivery attempt |
| `processing` | Currently being delivered |
| `delivered` | Successfully sent |
| `retry_pending` | Failed, scheduled for retry |
| `dead_letter` | Exceeded max failures — webhook deactivated |
| `cancelled` | Manually cancelled |
""")

    # ── Security ────────────────────────────────────────────────────
    with st.expander(":material/shield: Security & Rate Limits"):
        st.markdown("""
**Data Security:**
- API keys are stored as **SHA-256 hashes** — plain keys are never persisted
- Webhook targets and secrets are **encrypted at rest** using Fernet symmetric encryption
- Encryption key rotation is supported seamlessly (current + previous key)
- Webhook URLs are validated to **block private/local network destinations**
- Webhook payloads are signed with `X-Webhook-Signature` when a secret is configured

**Rate Limits:**

| Resource | Limit |
|----------|-------|
| API key requests | 1,000 per hour per key |
| Webhook test endpoint | 30 per hour per user |
| Feed response caching | 15 minutes TTL |

**Per-User Quotas** (varies by environment):

| Resource | Development | Production |
|----------|-------------|------------|
| API Keys | 20 | 5 |
| Custom Feeds | 20 | 5 |
| Bundles | 10 | 5 |
| Feeds per Bundle | 20 | 10 |
| Webhooks | 10 | 3 |
| Min Batch Interval | 5 min | 15 min |
| Max Items per Batch | 30 | 10 |

**Delivery Settings:**

| Setting | Value |
|---------|-------|
| Delivery timeout | 5 seconds per attempt |
| Delivery history retention | 30 days |
| Dead letter threshold | Configurable per webhook (1–20, default 5) |
""")


@require_auth
def main() -> None:
    # Sidebar
    with st.sidebar:
        username = st.session_state.get("username", "User")
        st.markdown(f"### :material/person: {username}")
        st.divider()
        if st.button(":material/logout: Logout", use_container_width=True):
            logout()
    
    st.title(":material/hub: Integrations")
    st.caption("Manage API keys, custom feeds, bundles, and webhooks.")

    if not config.ENABLE_INTEGRATIONS:
        st.info(":material/block: Integrations are disabled in configuration. Set `ENABLE_INTEGRATION_API=true` to enable this feature.")
        return

    if st.button(":material/refresh: Refresh", use_container_width=False):
        st.rerun()

    with show_loading("Loading integration data..."):
        data = _load_integrations_data()

    if data.get("disabled"):
        st.info(":material/block: Integrations are disabled on the backend. Enable `ENABLE_INTEGRATION_API` to use this page.")
        return

    errors = data.get("errors", [])
    for error in errors:
        show_error(f"Failed to load {error}")

    tabs = st.tabs([
        ":material/key: API Keys",
        ":material/rss_feed: Custom Feeds",
        ":material/folder_special: Bundles",
        ":material/webhook: Webhooks",
        ":material/bar_chart: Usage",
        ":material/menu_book: Documentation",
    ])

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
    with tabs[5]:
        _show_documentation()


if __name__ == "__main__":
    main()
