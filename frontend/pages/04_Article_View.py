import time
import streamlit as st
from services.api_service import api_service
from utils.auth import init_auth_state, require_auth
from utils.navigation import switch_page
from utils.ui_helpers import (
    init_page_config,
    apply_custom_css,
    format_date,
    show_error,
    show_loading,
    show_success,
    show_toast,
)

# Initialize
init_page_config("Article | News Summarizer", "")
apply_custom_css()
init_auth_state()

# Track reading time
if "article_start_time" not in st.session_state:
    st.session_state.article_start_time = None


@require_auth
def main() -> None:
    """Article detail view"""

    article_id = st.session_state.get("selected_article")

    if not article_id:
        st.warning("No article selected. Please select an article from the feed.")
        if st.button("Back to Feed"):
            switch_page("news-feed")
        st.stop()

    if st.session_state.article_start_time is None:
        st.session_state.article_start_time = time.time()

    with show_loading("Loading article..."):
        result = api_service.get_article(article_id)

    if not result["success"]:
        show_error(f"Failed to load article: {result.get('error')}")
        if st.button("Back to Feed"):
            switch_page("news-feed")
        st.stop()

    article = result["data"]

    # Header with back button
    col1, _ = st.columns([4, 1])
    with col1:
        if st.button("Back to Feed"):
            reading_time = int(time.time() - st.session_state.article_start_time)
            api_service.submit_feedback(
                article_id=article_id,
                feedback_type="neutral",
                time_spent_seconds=reading_time,
            )
            st.session_state.article_start_time = None
            switch_page("news-feed")

    st.divider()

    st.markdown(f"# {article.get('title', 'Untitled')}")

    # Metadata
    col1, col2, col3 = st.columns(3)
    with col1:
        st.caption(f"Source: {article.get('source_name', 'Unknown')}")
    with col2:
        st.caption(f"Published: {format_date(article.get('published_date', ''))}")
    with col3:
        if article.get("author"):
            st.caption(f"Author: {article.get('author')}")

    if article.get("topics"):
        topics = article["topics"][:5]
        col_spec = [1] * len(topics) + [max(1, 12 - len(topics))]
        topic_cols = st.columns(col_spec, gap="small")
        for i, topic in enumerate(topics):
            with topic_cols[i]:
                st.badge(topic, color="blue")

    st.divider()

    tab1, tab2, tab3 = st.tabs(["Full Article", "Summary", "Feedback"])

    with tab1:
        if article.get("image_url"):
            st.image(article["image_url"], use_container_width=True)

        st.markdown("### Article Content")
        content = article.get("content", "")
        if content:
            st.markdown(content)

            word_count = article.get("word_count", len(content.split()))
            reading_time_min = max(1, word_count // 200)

            col1, col2 = st.columns(2)
            with col1:
                st.metric("Word Count", f"{word_count:,}")
            with col2:
                st.metric("Reading Time", f"{reading_time_min} min")
        else:
            st.info("Full content not available")

        if article.get("url"):
            st.markdown(f"[Read on {article.get('source', 'source')}]({article['url']})")

    with tab2:
        st.markdown("### Summary")

        existing_summary = article.get("summary")

        if existing_summary:
            st.success("Summary available!")
            st.markdown(existing_summary)
        else:
            st.info("No summary available yet")

        col1, col2, col3 = st.columns([1, 2, 1])
        with col2:
            if st.button("Generate Summary", use_container_width=True, type="primary"):
                with show_loading("Generating summary..."):
                    summary_result = api_service.summarize_article(
                        article_id=article_id,
                        summary_length="medium",
                    )

                if summary_result["success"]:
                    summary = summary_result["data"].get("summary", "")
                    st.session_state[f"summary_{article_id}"] = summary
                    show_success("Summary generated successfully!")
                    st.rerun()
                else:
                    show_error(f"Failed to generate summary: {summary_result.get('error')}")

        if f"summary_{article_id}" in st.session_state:
            st.divider()
            st.markdown("#### Generated Summary")
            st.markdown(st.session_state[f"summary_{article_id}"])

    with tab3:
        st.markdown("### Your Feedback")
        st.caption("Help us improve your recommendations by rating this article")

        feedback_options = [
            ("Liked It", "positive", "primary"),
            ("Neutral", "neutral", "secondary"),
            ("Not Interested", "negative", "secondary"),
        ]
        cols = st.columns(3)
        for col, (label, ftype, btype) in zip(cols, feedback_options):
            with col:
                if st.button(label, use_container_width=True, type=btype):
                    reading_time = int(time.time() - st.session_state.article_start_time)
                    result = api_service.submit_feedback(
                        article_id=article_id,
                        feedback_type=ftype,
                        time_spent_seconds=reading_time,
                    )
                    if result["success"]:
                        show_toast("Thanks for your feedback!")

        st.divider()

        st.markdown("#### Tell us more (optional)")
        feedback_text = st.text_area(
            "What did you think about this article?",
            placeholder="Your thoughts help us improve...",
            height=100,
        )

        if st.button("Submit Detailed Feedback"):
            if feedback_text:
                show_success("Thank you for your detailed feedback!")
            else:
                st.warning("Please enter some feedback first")

    st.divider()

    st.markdown("### Related Articles")
    st.caption("You might also be interested in...")

    if article.get("topics"):
        with show_loading("Loading related articles..."):
            result = api_service.get_latest_news(
                page=1,
                limit=6,
                topics=article["topics"][:3],
                language="en",
            )

        if result["success"]:
            all_articles = result["data"].get("articles", [])
            related_articles = [
                a for a in all_articles
                if str(a.get("article_id", a.get("id"))) != str(article_id)
            ][:3]

            if related_articles:
                cols = st.columns(3)
                for idx, related in enumerate(related_articles):
                    with cols[idx]:
                        title = related.get("title", "Untitled")
                        display_title = title[:80] + "..." if len(title) > 80 else title
                        st.markdown(f"**{display_title}**")
                        st.caption(
                            f"{related.get('source_name', 'Unknown')}  •  "
                            f"{format_date(related.get('published_date', ''))}"
                        )
                        if related.get("topics"):
                            for topic in related["topics"][:2]:
                                st.badge(topic, color="blue")
                        if st.button("Read", key=f"related_{idx}"):
                            st.session_state.selected_article = str(
                                related.get("article_id", related.get("id"))
                            )
                            st.session_state.article_start_time = None
                            st.rerun()
            else:
                st.info("No related articles found.")
        else:
            st.info("Could not load related articles.")
    else:
        st.info("No topics available to find related articles.")


if __name__ == "__main__":
    main()
