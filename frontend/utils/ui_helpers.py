from datetime import datetime
from typing import List
from urllib.parse import quote
import re
import streamlit as st

from frontend_config import config
from utils.navigation import switch_page


def show_toast(message: str, icon: str = "", duration: int = 4) -> None:
    """Show toast notification with configurable duration (seconds)."""
    kwargs: dict = {"duration": int(duration)}
    if icon:
        kwargs["icon"] = icon
    st.toast(message, **kwargs)


def format_date(date_str: str) -> str:
    """Format date string for display"""
    if not date_str:
        return ""
    try:
        dt = datetime.fromisoformat(date_str.replace("Z", "+00:00"))
        now = datetime.now(dt.tzinfo)
        diff = now - dt

        if diff.days == 0:
            if diff.seconds < 3600:
                minutes = max(1, diff.seconds // 60)
                return f"{minutes} minutes ago"
            hours = max(1, diff.seconds // 3600)
            return f"{hours} hours ago"
        if diff.days == 1:
            return "Yesterday"
        if diff.days < 7:
            return f"{diff.days} days ago"
        return dt.strftime("%B %d, %Y")
    except Exception:
        return date_str


def show_article_card(article: dict, show_feedback: bool = True) -> None:
    """Display article card with styled container."""
    article_id = str(article.get("article_id", article.get("id", "")))
    source_name = article.get("source_name", "Unknown Source")
    published_date = article.get("published_date")

    with st.container(border=True):
        # Title
        title = article.get("title", "Untitled")
        st.markdown(f"#### {title}")

        # Metadata row
        meta_parts = [f":material/newspaper: **{source_name}**"]
        if published_date:
            meta_parts.append(f":material/schedule: {format_date(published_date)}")
        st.caption("  \u2009\u2022\u2009  ".join(meta_parts))

        # Topics
        if article.get("topics"):
            topics = article["topics"][:3]
            cols = st.columns(len(topics) + 1, gap="small")
            for i, topic in enumerate(topics):
                with cols[i]:
                    st.badge(topic, color="blue")

        # Content preview
        content = article.get("content", "")
        if content:
            preview = content[:250] + "..." if len(content) > 250 else content
            st.caption(preview)

        # Actions — icons + labels
        action_cols = st.columns([1, 1, 1, 3] if show_feedback else [1, 5])

        with action_cols[0]:
            if st.button(
                ":material/menu_book: Read",
                key=f"read_{article_id}",
                use_container_width=True,
                type="primary",
            ):
                st.session_state.selected_article = article_id
                switch_page("article-view")

        if show_feedback:
            with action_cols[1]:
                if st.button(
                    ":material/thumb_up: Like",
                    key=f"like_{article_id}",
                    use_container_width=True,
                ):
                    from services.api_service import api_service

                    result = api_service.submit_feedback(article_id, "positive")
                    if result["success"]:
                        show_toast("Thanks for the feedback!", icon="\U0001f44d")

            with action_cols[2]:
                if st.button(
                    ":material/thumb_down: Dislike",
                    key=f"dislike_{article_id}",
                    use_container_width=True,
                ):
                    from services.api_service import api_service

                    result = api_service.submit_feedback(article_id, "negative")
                    if result["success"]:
                        show_toast("Thanks for the feedback!")


def show_loading(message: str = "Loading...", show_time: bool = True):
    """Show loading spinner with elapsed time."""
    return st.spinner(message, show_time=show_time)


def init_page_config(page_title: str, page_icon: str = "", layout: str = "wide") -> None:
    """Initialize page configuration"""
    st.set_page_config(
        page_title=page_title,
        page_icon=page_icon,
        layout=layout,
        initial_sidebar_state="expanded",
    )
    st.logo(":material/newspaper:")


def apply_custom_css() -> None:
    """Apply MD3-aligned CSS for custom HTML components.

    Widget styling (buttons, inputs, tabs, sidebar, etc.) is handled entirely
    by Streamlit's native theme in .streamlit/config.toml (Streamlit ≥ 1.54).
    This function only provides styles for custom HTML rendered via
    st.markdown(unsafe_allow_html=True): hero, feature-cards, workflow steps,
    and the footer.
    """
    st.markdown(
        """
    <style>
    /* ── MD3 Design Tokens (for custom HTML components only) ──
       Widget/component theming lives in .streamlit/config.toml.
       These CSS variables mirror the config values so custom HTML
       stays visually consistent. */
    :root {
        --md-primary: #006B5E;
        --md-on-primary: #ffffff;
        --md-on-surface: #191C1B;
        --md-on-surface-variant: #3F4945;
        --md-outline-variant: #BFC9C3;
        --md-surface: #FBFDF9;
        --md-surface-container-low: #F0F4F1;
        --md-surface-container: #E8ECE9;
        --md-shape-medium: 0.75rem;
        --md-shape-large: 1rem;
        --md-shape-xl: 1.75rem;
        /* MD3 Elevation tokens */
        --md-elevation-1: 0 1px 2px rgba(0,0,0,0.3), 0 1px 3px 1px rgba(0,0,0,0.15);
        --md-elevation-2: 0 1px 2px rgba(0,0,0,0.3), 0 2px 6px 2px rgba(0,0,0,0.15);
    }

    /* ── Layout ── */
    .block-container {
        padding-top: 2rem;
        max-width: 1200px;
    }

    /* ── MD3 State Layer: subtle hover lift for buttons ── */
    .stButton > button:hover {
        transform: translateY(-1px);
    }
    .stButton > button:active {
        transform: translateY(0);
    }

    /* ── Hero (Home page) ── */
    .hero {
        background: var(--md-surface);
        border: 1px solid var(--md-outline-variant);
        border-radius: var(--md-shape-xl);
        padding: 3rem;
        box-shadow: var(--md-elevation-2);
        margin-bottom: 2rem;
        text-align: center;
    }

    .hero h1 {
        font-size: 2.4rem;
        margin-bottom: 0.5rem;
    }

    .hero-badge {
        display: inline-block;
        padding: 0.35rem 0.9rem;
        border-radius: 999px;
        background: rgba(0, 107, 94, 0.08);
        color: var(--md-primary);
        font-weight: 500;
        font-size: 0.85rem;
        margin-bottom: 1rem;
    }
    .hero-badge-icon {
        display: inline-flex;
        align-items: center;
        justify-content: center;
        width: 1.25rem;
        height: 1.25rem;
        border-radius: 999px;
        border: 1px solid rgba(0, 107, 94, 0.35);
        font-size: 0.68rem;
        margin-right: 0.45rem;
        vertical-align: middle;
        letter-spacing: 0.02em;
    }

    .hero-subtitle {
        color: var(--md-on-surface-variant);
        font-size: 1.1rem;
        line-height: 1.6;
        max-width: 540px;
        margin: 0 auto;
    }

    /* ── Feature cards (Home page) ── */
    .feature-card {
        background: var(--md-surface);
        border: 1px solid var(--md-outline-variant);
        border-radius: var(--md-shape-large);
        padding: 1.5rem;
        box-shadow: var(--md-elevation-1);
        height: 100%;
        transition: transform 0.2s cubic-bezier(0.2, 0, 0, 1),
                    box-shadow 0.2s cubic-bezier(0.2, 0, 0, 1);
    }

    .feature-card:hover {
        transform: translateY(-4px);
        box-shadow: var(--md-elevation-2);
    }

    .feature-card .card-icon {
        display: inline-flex;
        align-items: center;
        justify-content: center;
        min-width: 2.6rem;
        height: 2.1rem;
        border-radius: 999px;
        padding: 0 0.75rem;
        background: rgba(0, 107, 94, 0.1);
        border: 1px solid rgba(0, 107, 94, 0.2);
        color: var(--md-primary);
        font-size: 0.75rem;
        font-weight: 600;
        margin-bottom: 0.6rem;
        letter-spacing: 0.04em;
    }

    .feature-card h4 {
        margin-bottom: 0.3rem;
    }

    .subtle {
        color: var(--md-on-surface-variant);
        font-size: 0.92rem;
        line-height: 1.5;
    }

    /* ── Workflow steps (Home page) ── */
    .workflow-step {
        display: flex;
        align-items: flex-start;
        gap: 1rem;
        margin-bottom: 1.2rem;
    }

    .step-number {
        flex-shrink: 0;
        width: 36px;
        height: 36px;
        border-radius: 50%;
        background: var(--md-primary);
        color: var(--md-on-primary);
        display: flex;
        align-items: center;
        justify-content: center;
        font-weight: 500;
        font-size: 0.95rem;
    }

    .step-content h4 {
        margin: 0 0 0.15rem 0;
        font-size: 1rem;
    }

    .step-content p {
        margin: 0;
        color: var(--md-on-surface-variant);
        font-size: 0.9rem;
    }

    /* ── Footer ── */
    .app-footer {
        text-align: center;
        padding: 2rem 0;
        color: var(--md-on-surface-variant);
        font-size: 0.85rem;
    }

    .app-footer a {
        color: var(--md-primary);
        text-decoration: none;
    }
    </style>
        """,
        unsafe_allow_html=True,
    )


def show_error(message: str) -> None:
    """Display error message"""
    st.error(message)


def show_success(message: str) -> None:
    """Display success message"""
    st.success(message)


def render_contact_developer_option() -> None:
    """Render a sidebar action to contact the developer."""
    st.divider()
    st.markdown("### :material/person: Contact")

    if config.DEVELOPER_CONTACT_URL:
        st.link_button(
            ":material/language: Website",
            config.DEVELOPER_CONTACT_URL,
            use_container_width=True,
        )

    social_links = [
        (":material/code: GitHub", config.DEVELOPER_GITHUB_URL),
        (":material/work: LinkedIn", config.DEVELOPER_LINKEDIN_URL),
        (":material/campaign: Twitter/X", config.DEVELOPER_TWITTER_URL),
    ]
    for label, target in social_links:
        if target:
            st.link_button(label, target, use_container_width=True)

    with st.expander("Let's connect", expanded=False):
        name = st.text_input("Name", key="dev_contact_name")
        email = st.text_input("Email", key="dev_contact_email")
        message = st.text_area("Message", key="dev_contact_message", height=110)

        send_requested = st.button(
            ":material/send: Send Message",
            key="dev_contact_submit",
            use_container_width=True,
        )
        if send_requested:
            if not name.strip() or not email.strip() or not message.strip():
                st.error("Please fill name, email, and message.")
            elif not re.match(r"^[^@\s]+@[^@\s]+\.[^@\s]+$", email.strip()):
                st.error("Please enter a valid email address.")
            else:
                from services.api_service import api_service

                with st.spinner("Sending message..."):
                    result = api_service.contact_developer(
                        name=name.strip(),
                        email=email.strip(),
                        message=message.strip(),
                    )

                if result.get("success"):
                    st.success("Message sent to developer.")
                    st.session_state.pop("dev_contact_name", None)
                    st.session_state.pop("dev_contact_email", None)
                    st.session_state.pop("dev_contact_message", None)
                    st.rerun()
                else:
                    st.error(result.get("error", "Failed to send message."))
                    if config.DEVELOPER_CONTACT_EMAIL:
                        subject = quote(f"Let's connect - {name.strip()}")
                        body = quote(
                            f"Name: {name.strip()}\n"
                            f"Email: {email.strip()}\n\n"
                            f"Message:\n{message.strip()}\n"
                        )
                        mailto_link = f"mailto:{config.DEVELOPER_CONTACT_EMAIL}?subject={subject}&body={body}"
                        st.link_button(
                            ":material/open_in_new: Open Email Client (Fallback)",
                            mailto_link,
                            use_container_width=True,
                        )

    if not any(
        [
            config.DEVELOPER_CONTACT_URL,
            config.DEVELOPER_GITHUB_URL,
            config.DEVELOPER_LINKEDIN_URL,
            config.DEVELOPER_TWITTER_URL,
            config.DEVELOPER_CONTACT_EMAIL,
        ]
    ):
        st.caption("Developer links are not configured.")
