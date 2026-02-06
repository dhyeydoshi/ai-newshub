from datetime import datetime
from typing import List
import streamlit as st


def show_toast(message: str, icon: str = "", duration: int = 3) -> None:
    """Show toast notification"""
    if icon:
        st.toast(message, icon=icon)
    else:
        st.toast(message)
    _ = duration


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
    """Display article card"""
    with st.container():
        st.markdown(f"### {article.get('title', 'Untitled')}")

        source_name = article.get("source_name", "Unknown Source")
        published_date = article.get("published_date")

        if published_date:
            if isinstance(published_date, str):
                try:
                    date_obj = datetime.fromisoformat(published_date.replace("Z", "+00:00"))
                    formatted_date = date_obj.strftime("%B %d, %Y at %I:%M %p")
                except Exception:
                    formatted_date = published_date
            elif isinstance(published_date, datetime):
                formatted_date = published_date.strftime("%B %d, %Y at %I:%M %p")
            else:
                formatted_date = str(published_date)
        else:
            formatted_date = "Unknown date"

        # Metadata
        col1, col2, col3 = st.columns([2, 2, 1])
        with col1:
            st.caption(source_name)
        with col2:
            st.caption(formatted_date)
        with col3:
            if article.get("topics"):
                st.caption(", ".join(article["topics"][:2]))

        # Summary or content preview
        summary = article.get("summary", article.get("content", ""))
        if summary:
            preview = summary[:300] + "..." if len(summary) > 300 else summary
            st.write(preview)

        # Actions
        col1, col2, col3, _ = st.columns([1, 1, 1, 3])

        article_id = str(article.get("article_id", article.get("id", "")))

        with col1:
            if st.button("Read", key=f"read_{article_id}"):
                st.session_state.selected_article = article_id
                st.switch_page("pages/04_Article_View.py")

        if show_feedback:
            with col2:
                if st.button("Like", key=f"like_{article_id}"):
                    from services.api_service import api_service

                    result = api_service.submit_feedback(article_id, "positive")
                    if result["success"]:
                        show_toast("Feedback submitted!")

            with col3:
                if st.button("Dislike", key=f"dislike_{article_id}"):
                    from services.api_service import api_service

                    result = api_service.submit_feedback(article_id, "negative")
                    if result["success"]:
                        show_toast("Feedback submitted!")

        st.divider()


def show_loading(message: str = "Loading..."):
    """Show loading spinner"""
    return st.spinner(message)


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
        --accent-2: #f08c42;
        --card: #ffffff;
        --border: #e6e1d7;
        --shadow: 0 18px 40px rgba(16, 24, 40, 0.08);
    }

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

    .stButton > button {
        border-radius: 999px;
        padding: 0.6rem 1.1rem;
        border: 1px solid transparent;
        background: var(--accent);
        color: #ffffff;
        font-weight: 600;
        transition: transform 0.15s ease, box-shadow 0.15s ease;
    }

    .stButton > button:hover {
        transform: translateY(-1px);
        box-shadow: 0 10px 20px rgba(31, 122, 106, 0.22);
    }

    .stButton > button:focus {
        outline: none;
        box-shadow: 0 0 0 3px rgba(31, 122, 106, 0.25);
    }

    .stTextInput > div > div > input,
    .stSelectbox > div > div > select,
    .stTextArea textarea {
        border-radius: 12px;
        border: 1px solid var(--border);
        padding: 0.6rem 0.8rem;
    }

    [data-testid="stSidebar"] {
        background: #fbfaf7;
        border-right: 1px solid var(--border);
    }

    hr {
        margin: 1.5rem 0;
        border: none;
        border-top: 1px solid var(--border);
    }

    .hero {
        background: var(--card);
        border: 1px solid var(--border);
        border-radius: 24px;
        padding: 2.5rem;
        box-shadow: var(--shadow);
        margin-bottom: 2rem;
    }

    .hero-badge {
        display: inline-block;
        padding: 0.35rem 0.9rem;
        border-radius: 999px;
        background: rgba(31, 122, 106, 0.12);
        color: var(--accent);
        font-weight: 600;
        font-size: 0.85rem;
        margin-bottom: 1rem;
    }

    .hero-subtitle {
        color: var(--muted);
        font-size: 1.1rem;
        line-height: 1.6;
    }

    .feature-card {
        background: var(--card);
        border: 1px solid var(--border);
        border-radius: 18px;
        padding: 1.4rem;
        box-shadow: 0 10px 30px rgba(16, 24, 40, 0.06);
        height: 100%;
    }

    .feature-card h4 {
        margin-bottom: 0.5rem;
    }

    .subtle {
        color: var(--muted);
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


def show_info(message: str) -> None:
    """Display info message"""
    st.info(message)


def show_warning(message: str) -> None:
    """Display warning message"""
    st.warning(message)


def paginate_list(items: List, page: int, items_per_page: int) -> tuple:
    """Paginate a list of items"""
    total_pages = (len(items) + items_per_page - 1) // items_per_page
    start_idx = (page - 1) * items_per_page
    end_idx = start_idx + items_per_page
    return items[start_idx:end_idx], total_pages


def show_pagination(current_page: int, total_pages: int, key_prefix: str = "page") -> int:
    """Display pagination controls"""
    col1, col2, col3 = st.columns([1, 2, 1])

    with col1:
        if current_page > 1:
            if st.button("Previous", key=f"{key_prefix}_prev"):
                return current_page - 1

    with col2:
        st.write(f"Page {current_page} of {total_pages}")

    with col3:
        if current_page < total_pages:
            if st.button("Next", key=f"{key_prefix}_next"):
                return current_page + 1

    return current_page
