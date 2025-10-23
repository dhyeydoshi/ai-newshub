import streamlit as st
from services.api_service import api_service
from utils.auth import init_auth_state, require_auth
from utils.ui_helpers import (
    init_page_config, apply_custom_css, format_date,
    show_error, show_loading, show_success, show_toast
)
import time

# Initialize
init_page_config("Article | News Summarizer", "📖")
apply_custom_css()
init_auth_state()

# Track reading time
if "article_start_time" not in st.session_state:
    st.session_state.article_start_time = None


@require_auth
def main():
    """Article detail view"""

    # Get article ID from session state
    article_id = st.session_state.get("selected_article")

    if not article_id:
        st.warning("No article selected. Please select an article from the feed.")
        if st.button("← Back to Feed"):
            st.switch_page("pages/03_📱_News_Feed.py")
        st.stop()

    # Start tracking reading time
    if st.session_state.article_start_time is None:
        st.session_state.article_start_time = time.time()

    # Load article details
    with show_loading("Loading article..."):
        result = api_service.get_article(article_id)

    if not result["success"]:
        show_error(f"Failed to load article: {result.get('error')}")
        if st.button("← Back to Feed"):
            st.switch_page("pages/03_📱_News_Feed.py")
        st.stop()

    article = result["data"]

    # Header with back button
    col1, col2 = st.columns([4, 1])
    with col1:
        if st.button("← Back to Feed"):
            # Calculate reading time
            reading_time = int(time.time() - st.session_state.article_start_time)
            # Submit engagement feedback
            api_service.submit_feedback(
                article_id=article_id,
                feedback_type="neutral",
                time_spent_seconds=reading_time
            )
            st.session_state.article_start_time = None
            st.switch_page("pages/03_📱_News_Feed.py")

    st.divider()

    # Article header
    st.markdown(f"# {article.get('title', 'Untitled')}")

    # Metadata
    col1, col2, col3 = st.columns(3)
    with col1:
        st.caption(f"📰 **Source:** {article.get('source_name', 'Unknown')}")
    with col2:
        st.caption(f"🕒 **Published:** {format_date(article.get('published_date', ''))}")
    with col3:
        if article.get('author'):
            st.caption(f"✍️ **Author:** {article.get('author')}")

    # Topics
    if article.get('topics'):
        topics_html = " ".join([
            f'<span style="background-color: #e3f2fd; padding: 4px 12px; border-radius: 12px; margin-right: 8px; font-size: 0.9em;">🏷️ {topic}</span>'
            for topic in article['topics'][:5]
        ])
        st.markdown(topics_html, unsafe_allow_html=True)

    st.divider()

    # Tabs for content and summary
    tab1, tab2, tab3 = st.tabs(["📄 Full Article", "✨ AI Summary", "💬 Feedback"])

    with tab1:
        # Article image
        if article.get('image_url'):
            st.image(article['image_url'], use_container_width=True)

        # Full content
        st.markdown("### Article Content")
        content = article.get('content', '')
        if content:
            st.markdown(content)

            # Reading stats
            word_count = article.get('word_count', len(content.split()))
            reading_time_min = max(1, word_count // 200)

            col1, col2 = st.columns(2)
            with col1:
                st.metric("📊 Word Count", f"{word_count:,}")
            with col2:
                st.metric("⏱️ Reading Time", f"{reading_time_min} min")
        else:
            st.info("Full content not available")

        # Source link
        if article.get('url'):
            st.markdown(f"[🔗 Read on {article.get('source', 'source')}]({article['url']})")

    with tab2:
        st.markdown("### AI-Generated Summary")

        # Check if summary exists
        existing_summary = article.get('summary')

        if existing_summary:
            st.success("Summary available!")
            st.markdown(existing_summary)
        else:
            st.info("No summary available yet")

        # Generate summary button
        col1, col2, col3 = st.columns([1, 2, 1])
        with col2:
            if st.button("✨ Generate AI Summary", use_container_width=True, type="primary"):
                with show_loading("Generating summary with AI..."):
                    summary_result = api_service.summarize_article(
                        article_id=article_id,
                        summary_length="medium"
                    )

                if summary_result["success"]:
                    summary = summary_result["data"].get("summary", "")
                    st.session_state[f"summary_{article_id}"] = summary
                    show_success("Summary generated successfully!")
                    st.rerun()
                else:
                    show_error(f"Failed to generate summary: {summary_result.get('error')}")

        # Display generated summary if available
        if f"summary_{article_id}" in st.session_state:
            st.divider()
            st.markdown("#### Generated Summary")
            st.markdown(st.session_state[f"summary_{article_id}"])

    with tab3:
        st.markdown("### Your Feedback")
        st.caption("Help us improve your recommendations by rating this article")

        # Feedback buttons
        col1, col2, col3 = st.columns(3)

        with col1:
            if st.button("👍 Liked It", use_container_width=True, type="primary"):
                reading_time = int(time.time() - st.session_state.article_start_time)
                result = api_service.submit_feedback(
                    article_id=article_id,
                    feedback_type="positive",
                    time_spent_seconds=reading_time
                )
                if result["success"]:
                    show_toast("Thanks for your feedback!", "✅")
                    st.balloons()

        with col2:
            if st.button("😐 Neutral", use_container_width=True):
                reading_time = int(time.time() - st.session_state.article_start_time)
                result = api_service.submit_feedback(
                    article_id=article_id,
                    feedback_type="neutral",
                    time_spent_seconds=reading_time
                )
                if result["success"]:
                    show_toast("Thanks for your feedback!", "✅")

        with col3:
            if st.button("👎 Not Interested", use_container_width=True):
                reading_time = int(time.time() - st.session_state.article_start_time)
                result = api_service.submit_feedback(
                    article_id=article_id,
                    feedback_type="negative",
                    time_spent_seconds=reading_time
                )
                if result["success"]:
                    show_toast("Thanks for your feedback!", "✅")

        st.divider()

        # Additional feedback
        st.markdown("#### Tell us more (optional)")
        feedback_text = st.text_area(
            "What did you think about this article?",
            placeholder="Your thoughts help us improve...",
            height=100
        )

        if st.button("Submit Detailed Feedback"):
            if feedback_text:
                show_success("Thank you for your detailed feedback!")
            else:
                st.warning("Please enter some feedback first")

    st.divider()

    # Related articles section
    st.markdown("### 📚 Related Articles")
    st.caption("You might also be interested in...")

    # Load related articles (based on topics)
    if article.get('topics'):
        with show_loading("Loading related articles..."):
            result = api_service.get_latest_news(
                page=1,
                limit=3,
                topics=article['topics'][:2]
            )

        if result["success"]:
            related_articles = result["data"].get("articles", [])[:3]

            cols = st.columns(3)
            for idx, related in enumerate(related_articles):
                with cols[idx]:
                    st.markdown(f"**{related.get('title', 'Untitled')[:50]}...**")
                    st.caption(f"📰 {related.get('source', 'Unknown')}")
                    if st.button("Read", key=f"related_{idx}"):
                        st.session_state.selected_article = related.get('article_id', related.get('id'))
                        st.session_state.article_start_time = None
                        st.rerun()


if __name__ == "__main__":
    main()

