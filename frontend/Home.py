import streamlit as st
from frontend_config import config
from utils.auth import init_auth_state, logout
from utils.ui_helpers import init_page_config, apply_custom_css

# Initialize page configuration
init_page_config(
    page_title=config.PAGE_TITLE,
    page_icon=config.PAGE_ICON,
    layout=config.LAYOUT,
)

# Apply custom styling
apply_custom_css()

# Initialize authentication state
init_auth_state()


def main() -> None:
    """Landing page"""
    auth_notice = st.session_state.pop("auth_notice", None)
    if auth_notice:
        st.warning(auth_notice)

    st.markdown(
        """
        <div class="hero">
            <div class="hero-badge">News Aggregation + Personalization</div>
            <h1>Signal Over Noise</h1>
            <p class="hero-subtitle">
                Multi-source ingestion, clean summaries, and a feed that learns from what you read.
            </p>
        </div>
        """,
        unsafe_allow_html=True,
    )

    st.markdown("### Start here")

    if st.session_state.get("is_authenticated", False):
        st.success(f"Welcome back, **{st.session_state.get('username', 'User')}**!")
        col_a, col_b, col_c = st.columns(3)
        with col_a:
            if st.button("Open News Feed", use_container_width=True, type="primary"):
                st.switch_page("pages/03_News_Feed.py")
        with col_b:
            if st.button("View Profile", use_container_width=True):
                st.switch_page("pages/06_Profile.py")
        with col_c:
            if st.button("Logout", use_container_width=True):
                logout()
    else:
        col_a, col_b = st.columns(2)
        with col_a:
            if st.button("Log In", use_container_width=True, type="primary"):
                st.switch_page("pages/02_Login.py")
        with col_b:
            if st.button("Create Account", use_container_width=True):
                st.switch_page("pages/02_Login.py")

    st.divider()

    st.markdown("### What you get")
    col1, col2, col3 = st.columns(3)
    with col1:
        st.markdown(
            """
            <div class="feature-card">
                <h4>Multi-source coverage</h4>
                <p class="subtle">Aggregate NewsAPI, GDELT, and RSS into one stream.</p>
            </div>
            """,
            unsafe_allow_html=True,
        )
    with col2:
        st.markdown(
            """
            <div class="feature-card">
                <h4>Clean, fast summaries</h4>
                <p class="subtle">Scan key points quickly, then dive into full articles.</p>
            </div>
            """,
            unsafe_allow_html=True,
        )
    with col3:
        st.markdown(
            """
            <div class="feature-card">
                <h4>Personalized ranking</h4>
                <p class="subtle">Your feedback helps refine the feed over time.</p>
            </div>
            """,
            unsafe_allow_html=True,
        )

    st.divider()

    st.markdown("### Workflow")
    st.markdown(
        "1. Connect and aggregate sources. "
        "2. Read summaries and full stories. "
        "3. Give feedback to personalize your feed."
    )

    st.divider()

    st.markdown(
        """
        <div style='text-align: center; padding: 2rem 0; color: #666;'>
            <p>Built with FastAPI, PostgreSQL, Redis, and Reinforcement Learning</p>
            <p style='font-size: 0.9rem;'>
                (c) 2024 News Summarizer. All rights reserved.
            </p>
        </div>
        """,
        unsafe_allow_html=True,
    )


if __name__ == "__main__":
    main()
