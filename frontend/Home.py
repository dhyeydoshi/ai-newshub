"""
News Summarizer - Streamlit Frontend
Main Application Entry Point
"""
import streamlit as st
from frontend_config import config
from utils.auth import init_auth_state
from utils.ui_helpers import init_page_config, apply_custom_css

# Initialize page configuration
init_page_config(
    page_title=config.PAGE_TITLE,
    page_icon=config.PAGE_ICON,
    layout=config.LAYOUT
)

# Apply custom styling
apply_custom_css()

# Initialize authentication state
init_auth_state()

# Main Landing Page
def main():
    """Landing page"""

    # Header
    st.markdown("""
    <div style='text-align: center; padding: 2rem 0;'>
        <h1 style='font-size: 3rem; margin-bottom: 0;'>📰 News Summarizer</h1>
        <p style='font-size: 1.2rem; color: #666;'>
            AI-Powered News Aggregation & Personalized Recommendations
        </p>
    </div>
    """, unsafe_allow_html=True)

    # Hero section
    col1, col2 = st.columns([1, 1])

    with col1:
        st.markdown("""
        ### 🚀 Features
        
        - **🌐 Multi-Source Aggregation**: Get news from NewsAPI, GDELT, and RSS feeds
        - **🤖 AI Summaries**: Instant article summaries powered by GPT-4
        - **🎯 Personalized Feed**: Machine learning recommendations tailored to you
        - **📊 Smart Analytics**: Track your reading habits and preferences
        - **⚡ Real-time Updates**: Always stay informed with the latest news
        """)

    with col2:
        st.markdown("""
        ### 🎨 Why Choose Us?
        
        - **Advanced RL Algorithm**: Our recommendation engine learns from your behavior
        - **Secure & Private**: Enterprise-grade security with JWT authentication
        - **Clean Interface**: Beautiful, intuitive design for the best experience
        - **Fast & Responsive**: Optimized performance for seamless browsing
        """)

    st.divider()

    # Call to action
    col1, col2, col3 = st.columns([1, 2, 1])

    with col2:
        st.markdown("### 🔐 Get Started")

        if st.session_state.get("is_authenticated", False):
            st.success(f"Welcome back, **{st.session_state.get('username', 'User')}**!")

            col_a, col_b = st.columns(2)
            with col_a:
                if st.button("📱 Go to News Feed", use_container_width=True, type="primary"):
                    st.switch_page("pages/03_📱_News_Feed.py")
            with col_b:
                if st.button("👤 View Profile", use_container_width=True):
                    st.switch_page("pages/06_👤_Profile.py")
        else:
            col_a, col_b = st.columns(2)
            with col_a:
                if st.button("🔑 Login", use_container_width=True, type="primary"):
                    st.switch_page("pages/02_🔑_Login.py")
            with col_b:
                if st.button("📝 Register", use_container_width=True):
                    st.switch_page("pages/02_🔑_Login.py")

    st.divider()

    # Statistics
    st.markdown("### 📊 Platform Statistics")
    col1, col2, col3, col4 = st.columns(4)

    with col1:
        st.metric("Active Users", "10K+", "+15%")
    with col2:
        st.metric("Articles Processed", "100K+", "+25%")
    with col3:
        st.metric("News Sources", "50+", "+5")
    with col4:
        st.metric("Avg. Accuracy", "98%", "+2%")

    st.divider()

    # How it works
    st.markdown("### 🔄 How It Works")

    col1, col2, col3 = st.columns(3)

    with col1:
        st.markdown("""
        #### 1️⃣ Sign Up
        Create your free account in seconds. No credit card required.
        """)

    with col2:
        st.markdown("""
        #### 2️⃣ Explore
        Browse curated news from multiple sources. Get AI-powered summaries.
        """)

    with col3:
        st.markdown("""
        #### 3️⃣ Personalize
        Like articles you enjoy. Our AI learns your preferences over time.
        """)

    st.divider()

    # Footer
    st.markdown("""
    <div style='text-align: center; padding: 2rem 0; color: #666;'>
        <p>Built with ❤️ using FastAPI, PostgreSQL, Redis, and Reinforcement Learning</p>
        <p style='font-size: 0.9rem;'>
            © 2024 News Summarizer. All rights reserved. | 
            <a href='#'>Privacy Policy</a> | 
            <a href='#'>Terms of Service</a>
        </p>
    </div>
    """, unsafe_allow_html=True)


if __name__ == "__main__":
    main()

