"""
UI Helper Functions
Common UI components and utilities
"""
import streamlit as st
from datetime import datetime
from typing import Optional, List
import time


def show_toast(message: str, icon: str = "ℹ️", duration: int = 3):
    """Show toast notification"""
    st.toast(f"{icon} {message}", icon=icon)


def format_date(date_str: str) -> str:
    """Format date string for display"""
    try:
        dt = datetime.fromisoformat(date_str.replace('Z', '+00:00'))
        now = datetime.now(dt.tzinfo)
        diff = now - dt

        if diff.days == 0:
            if diff.seconds < 3600:
                return f"{diff.seconds // 60} minutes ago"
            else:
                return f"{diff.seconds // 3600} hours ago"
        elif diff.days == 1:
            return "Yesterday"
        elif diff.days < 7:
            return f"{diff.days} days ago"
        else:
            return dt.strftime("%B %d, %Y")
    except:
        return date_str


def show_article_card(article: dict, show_feedback: bool = True):
    """Display article card"""
    with st.container():
        st.markdown(f"### {article.get('title', 'Untitled')}")

        source_name = article.get('source_name', 'Unknown Source')
        published_date = article.get('published_date')

        if published_date:
            if isinstance(published_date, str):
                try:
                    date_obj = datetime.fromisoformat(published_date.replace('Z', '+00:00'))
                    formatted_date = date_obj.strftime('%B %d, %Y at %I:%M %p')
                except:
                    formatted_date = published_date
            elif isinstance(published_date, datetime):
                formatted_date = published_date.strftime('%B %d, %Y at %I:%M %p')
            else:
                formatted_date = str(published_date)
        else:
            formatted_date = 'Unknown date'



        # Metadata
        col1, col2, col3 = st.columns([2, 2, 1])
        with col1:
            st.caption(f"📰 {source_name}")
        with col2:
            st.caption(f"🕒 {formatted_date}")
        with col3:
            if article.get('topics'):
                st.caption(f"🏷️ {', '.join(article['topics'][:2])}")

        # Summary or content preview
        summary = article.get('summary', article.get('content', ''))
        if summary:
            st.write(summary[:300] + "..." if len(summary) > 300 else summary)

        # Actions
        col1, col2, col3, col4 = st.columns([1, 1, 1, 3])

        article_id = article.get('article_id', article.get('id', ''))

        with col1:
            if st.button("📖 Read", key=f"read_{article_id}"):
                st.session_state.selected_article = article_id
                st.switch_page("pages/04_📖_Article_View.py")

        if show_feedback:
            with col2:
                if st.button("👍", key=f"like_{article_id}"):
                    from services.api_service import api_service
                    result = api_service.submit_feedback(article_id, "positive")
                    if result["success"]:
                        show_toast("Feedback submitted!", "✅")

            with col3:
                if st.button("👎", key=f"dislike_{article_id}"):
                    from services.api_service import api_service
                    result = api_service.submit_feedback(article_id, "negative")
                    if result["success"]:
                        show_toast("Feedback submitted!", "✅")

        st.divider()


def show_loading(message: str = "Loading..."):
    """Show loading spinner"""
    return st.spinner(message)


def init_page_config(page_title: str, page_icon: str = "📰", layout: str = "wide"):
    """Initialize page configuration"""
    st.set_page_config(
        page_title=page_title,
        page_icon=page_icon,
        layout=layout,
        initial_sidebar_state="expanded"
    )


def apply_custom_css():
    """Apply custom CSS styling"""
    st.markdown("""
    <style>
    /* Main container */
    .main {
        padding: 2rem;
    }
    
    /* Article cards */
    .article-card {
        background: white;
        border-radius: 10px;
        padding: 1.5rem;
        margin-bottom: 1rem;
        box-shadow: 0 2px 4px rgba(0,0,0,0.1);
    }
    
    /* Buttons */
    .stButton > button {
        border-radius: 5px;
        transition: all 0.3s;
    }
    
    .stButton > button:hover {
        transform: translateY(-2px);
        box-shadow: 0 4px 8px rgba(0,0,0,0.2);
    }
    
    /* Headers */
    h1, h2, h3 {
        color: #1f1f1f;
    }
    
    /* Links */
    a {
        text-decoration: none;
        color: #0066cc;
    }
    
    a:hover {
        color: #0052a3;
    }
    
    /* Sidebar */
    .css-1d391kg {
        background-color: #f8f9fa;
    }
    
    /* Remove default padding */
    .block-container {
        padding-top: 2rem;
    }
    
    /* Custom divider */
    hr {
        margin: 1rem 0;
        border: none;
        border-top: 1px solid #e0e0e0;
    }
    
    /* Toast notifications */
    .stToast {
        background-color: #ffffff;
        border-left: 4px solid #4CAF50;
    }
    
    /* Input fields */
    .stTextInput > div > div > input {
        border-radius: 5px;
    }
    
    /* Select boxes */
    .stSelectbox > div > div > select {
        border-radius: 5px;
    }
    
    /* Cards hover effect */
    .element-container:hover {
        transform: scale(1.01);
        transition: transform 0.2s;
    }
    </style>
    """, unsafe_allow_html=True)


def show_error(message: str):
    """Display error message"""
    st.error(f"❌ {message}")


def show_success(message: str):
    """Display success message"""
    st.success(f"✅ {message}")


def show_info(message: str):
    """Display info message"""
    st.info(f"ℹ️ {message}")


def show_warning(message: str):
    """Display warning message"""
    st.warning(f"⚠️ {message}")


def paginate_list(items: List, page: int, items_per_page: int) -> tuple:
    """Paginate a list of items"""
    total_pages = (len(items) + items_per_page - 1) // items_per_page
    start_idx = (page - 1) * items_per_page
    end_idx = start_idx + items_per_page
    return items[start_idx:end_idx], total_pages


def show_pagination(current_page: int, total_pages: int, key_prefix: str = "page"):
    """Display pagination controls"""
    col1, col2, col3 = st.columns([1, 2, 1])

    with col1:
        if current_page > 1:
            if st.button("⬅️ Previous", key=f"{key_prefix}_prev"):
                return current_page - 1

    with col2:
        st.write(f"Page {current_page} of {total_pages}")

    with col3:
        if current_page < total_pages:
            if st.button("Next ➡️", key=f"{key_prefix}_next"):
                return current_page + 1

    return current_page

