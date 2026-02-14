from datetime import datetime
from typing import List
import streamlit as st

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


def apply_custom_css() -> None:
    """Apply custom CSS styling"""
    # Selectors below target Streamlit's public data-testid attributes and
    # stable CSS class names (stButton, stTextInput, stTabs, etc.).  These have
    # been stable across Streamlit 1.30 – 1.50.  If a future Streamlit release
    # renames them, the worst-case outcome is that custom colours / radii fall
    # back to Streamlit's defaults — no functionality is lost.
    st.markdown(
        """
    <style>
    @import url('https://fonts.googleapis.com/css2?family=IBM+Plex+Sans:wght@400;500;600&family=Space+Grotesk:wght@400;600;700&display=swap');

    :root {
        --bg-1: #f6f3ee;
        --bg-2: #eef4ff;
        --ink: #1f2933;
        --muted: #5b6470;
        --accent: #1f7a6a;
        --accent-light: rgba(31, 122, 106, 0.08);
        --accent-2: #f08c42;
        --card: #ffffff;
        --border: #e6e1d7;
        --shadow: 0 18px 40px rgba(16, 24, 40, 0.08);
        --shadow-sm: 0 4px 12px rgba(16, 24, 40, 0.05);
        --radius: 16px;
        --radius-sm: 10px;
    }

    /* ── Base ── */
    .stApp {
        background: radial-gradient(circle at top left, #ffffff 0%, var(--bg-2) 35%, var(--bg-1) 100%);
        color: var(--ink);
        font-family: 'IBM Plex Sans', system-ui, sans-serif;
    }

    h1, h2, h3, h4 {
        font-family: 'Space Grotesk', system-ui, sans-serif;
        letter-spacing: -0.02em;
        color: var(--ink);
    }

    .block-container {
        padding-top: 2rem;
        max-width: 1200px;
    }

    /* ── Buttons ── */
    .stButton > button {
        border-radius: 999px;
        padding: 0.55rem 1.2rem;
        border: 1px solid transparent;
        background: var(--accent);
        color: #ffffff;
        font-weight: 600;
        font-size: 0.88rem;
        transition: transform 0.18s ease, box-shadow 0.18s ease, background 0.18s ease;
    }

    .stButton > button:hover {
        transform: translateY(-2px);
        box-shadow: 0 8px 20px rgba(31, 122, 106, 0.22);
    }

    .stButton > button:active {
        transform: translateY(0);
    }

    .stButton > button:focus {
        outline: none;
        box-shadow: 0 0 0 3px rgba(31, 122, 106, 0.25);
    }

    /* ── Inputs ── */
    .stTextInput > div > div > input,
    .stSelectbox > div > div > select,
    .stTextArea textarea {
        border-radius: var(--radius-sm);
        border: 1px solid var(--border);
        padding: 0.6rem 0.8rem;
        transition: border 0.15s ease, box-shadow 0.15s ease;
    }

    .stTextInput > div > div > input:focus,
    .stTextArea textarea:focus {
        border-color: var(--accent);
        box-shadow: 0 0 0 3px var(--accent-light);
    }

    /* ── Sidebar (data-testid is Streamlit's public API for theming) ── */
    [data-testid="stSidebar"] {
        background: #fbfaf7;
        border-right: 1px solid var(--border);
    }

    [data-testid="stSidebar"] .stButton > button {
        font-size: 0.82rem;
        padding: 0.45rem 0.9rem;
    }

    /* ── Dividers ── */
    hr {
        margin: 1.5rem 0;
        border: none;
        border-top: 1px solid var(--border);
    }

    /* ── Hero ── */
    .hero {
        background: var(--card);
        border: 1px solid var(--border);
        border-radius: 24px;
        padding: 3rem;
        box-shadow: var(--shadow);
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
        background: var(--accent-light);
        color: var(--accent);
        font-weight: 600;
        font-size: 0.85rem;
        margin-bottom: 1rem;
    }

    .hero-subtitle {
        color: var(--muted);
        font-size: 1.1rem;
        line-height: 1.6;
        max-width: 540px;
        margin: 0 auto;
    }

    /* ── Feature cards ── */
    .feature-card {
        background: var(--card);
        border: 1px solid var(--border);
        border-radius: var(--radius);
        padding: 1.6rem;
        box-shadow: var(--shadow-sm);
        height: 100%;
        transition: transform 0.2s ease, box-shadow 0.2s ease;
    }

    .feature-card:hover {
        transform: translateY(-4px);
        box-shadow: var(--shadow);
    }

    .feature-card .card-icon {
        font-size: 2rem;
        margin-bottom: 0.6rem;
    }

    .feature-card h4 {
        margin-bottom: 0.4rem;
    }

    .subtle {
        color: var(--muted);
        font-size: 0.92rem;
        line-height: 1.5;
    }

    /* ── Article card ── */
    .article-card {
        background: var(--card);
        border: 1px solid var(--border);
        border-radius: var(--radius);
        padding: 1.4rem 1.6rem;
        margin-bottom: 0.8rem;
        box-shadow: var(--shadow-sm);
        transition: transform 0.2s ease, box-shadow 0.2s ease;
    }

    .article-card:hover {
        transform: translateY(-2px);
        box-shadow: var(--shadow);
    }

    .article-card h3 {
        font-size: 1.15rem;
        margin-bottom: 0.3rem;
        line-height: 1.35;
    }

    /* ── Workflow steps ── */
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
        background: var(--accent);
        color: #fff;
        display: flex;
        align-items: center;
        justify-content: center;
        font-weight: 700;
        font-size: 0.95rem;
        font-family: 'Space Grotesk', system-ui, sans-serif;
    }

    .step-content h4 {
        margin: 0 0 0.15rem 0;
        font-size: 1rem;
    }

    .step-content p {
        margin: 0;
        color: var(--muted);
        font-size: 0.9rem;
    }

    /* ── Metrics (data-testid="stMetric" is stable since 1.22) ── */
    [data-testid="stMetric"] {
        background: var(--card);
        border: 1px solid var(--border);
        border-radius: var(--radius-sm);
        padding: 0.8rem 1rem;
    }

    /* ── Tabs (data-baseweb is BaseWeb UI library used by Streamlit) ── */
    .stTabs [data-baseweb="tab-list"] {
        gap: 0.2rem;
    }

    .stTabs [data-baseweb="tab"] {
        border-radius: var(--radius-sm) var(--radius-sm) 0 0;
        font-weight: 500;
        padding: 0.55rem 1.1rem;
    }

    /* ── Expander ── */
    details summary {
        font-weight: 600;
        font-size: 0.95rem;
    }

    /* ── Related article card ── */
    .related-card {
        background: var(--card);
        border: 1px solid var(--border);
        border-radius: var(--radius-sm);
        padding: 1rem 1.2rem;
        height: 100%;
        transition: transform 0.2s ease, box-shadow 0.2s ease;
    }

    .related-card:hover {
        transform: translateY(-2px);
        box-shadow: var(--shadow-sm);
    }

    /* ── Footer ── */
    .app-footer {
        text-align: center;
        padding: 2rem 0;
        color: var(--muted);
        font-size: 0.85rem;
    }

    .app-footer a {
        color: var(--accent);
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
