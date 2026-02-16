import streamlit as st
from frontend_config import config
from utils.auth import init_auth_state, logout
from utils.navigation import switch_page
from utils.ui_helpers import init_page_config, apply_custom_css, render_contact_developer_option

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
    verify_token = st.query_params.get("verify_token")
    if isinstance(verify_token, list):
        verify_token = verify_token[0] if verify_token else ""
    verify_token = (verify_token or "").strip()
    if verify_token:
        st.session_state["email_verification_token"] = verify_token
        st.session_state["verify_show_token_form"] = True
        st.session_state["auth_view"] = "Verify Email"
        st.query_params.clear()
        switch_page("login")

    reset_token = st.query_params.get("reset_token")
    if isinstance(reset_token, list):
        reset_token = reset_token[0] if reset_token else ""
    reset_token = (reset_token or "").strip()
    if reset_token:
        st.session_state["password_reset_token"] = reset_token
        st.session_state["reset_show_token_form"] = True
        st.session_state["auth_view"] = "Reset Password"
        st.query_params.clear()
        switch_page("login")

    with st.sidebar:
        render_contact_developer_option()

    auth_notice = st.session_state.pop("auth_notice", None)
    if auth_notice:
        st.warning(auth_notice)

    # ?? Hero ??
    st.markdown(
        """
        <div class="hero">
            <div class="hero-badge"><span class="hero-badge-icon">RSS</span>News Aggregation + Personalization</div>
            <h1>Signal Over Noise</h1>
            <p class="hero-subtitle">
                Multi-source ingestion, curated content, and a feed that learns from what you read.
            </p>
        </div>
        """,
        unsafe_allow_html=True,
    )

    # ?? CTAs ??
    if st.session_state.get("is_authenticated", False):
        st.success(f"Welcome back, **{st.session_state.get('username', 'User')}**!")
        col_a, col_b, col_c = st.columns(3)
        with col_a:
            if st.button(
                ":material/newspaper: Open News Feed",
                use_container_width=True,
                type="primary",
            ):
                switch_page("news-feed")
        with col_b:
            if st.button(":material/person: View Profile", use_container_width=True):
                switch_page("profile")
        with col_c:
            if st.button(":material/logout: Logout", use_container_width=True):
                logout()
    else:
        col_a, col_b = st.columns(2)
        with col_a:
            if st.button(
                ":material/login: Log In",
                use_container_width=True,
                type="primary",
            ):
                switch_page("login")
        with col_b:
            if st.button(":material/person_add: Create Account", use_container_width=True):
                st.session_state["auth_view"] = "Register"
                switch_page("login")

    st.divider()

    # ?? Feature cards ??
    st.markdown("### What you get")
    col1, col2, col3 = st.columns(3)
    with col1:
        st.markdown(
            """
            <div class="feature-card">
                <div class="card-icon">INGEST</div>
                <h4>Multi-source coverage</h4>
                <p class="subtle">Aggregate NewsAPI, GDELT, and RSS into one stream. no tab-hopping required.</p>
            </div>
            """,
            unsafe_allow_html=True,
        )
    with col2:
        st.markdown(
            """
            <div class="feature-card">
                <div class="card-icon">READ</div>
                <h4>Clean, focused reading</h4>
                <p class="subtle">Full articles with key topics highlighted and related content at your fingertips.</p>
            </div>
            """,
            unsafe_allow_html=True,
        )
    with col3:
        st.markdown(
            """
            <div class="feature-card">
                <div class="card-icon">RANK</div>
                <h4>Personalized ranking</h4>
                <p class="subtle">Your feedback trains a ranking model so the feed gets smarter every day.</p>
            </div>
            """,
            unsafe_allow_html=True,
        )

    st.divider()

    # ?? Workflow ? numbered steps ??
    st.markdown("### How it works")
    st.markdown(
        """
        <div class="workflow-step">
            <div class="step-number">1</div>
            <div class="step-content">
                <h4>Connect &amp; aggregate sources</h4>
                <p>News is fetched automatically from dozens of RSS feeds, NewsAPI, and GDELT.</p>
            </div>
        </div>
        <div class="workflow-step">
            <div class="step-number">2</div>
            <div class="step-content">
                <h4>Read &amp; discover</h4>
                <p>Browse the latest articles, search by keyword, and explore related content.</p>
            </div>
        </div>
        <div class="workflow-step">
            <div class="step-number">3</div>
            <div class="step-content">
                <h4>Give feedback &amp; personalize</h4>
                <p>A thumbs-up or thumbs-down trains the model ? your feed improves with every interaction.</p>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    st.divider()

    st.markdown(
        """
        <div class="app-footer">
            <p>Built with FastAPI, PostgreSQL, Redis, and Reinforcement Learning</p>
        </div>
        """,
        unsafe_allow_html=True,
    )


if __name__ == "__main__":
    main()
