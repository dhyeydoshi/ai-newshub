import streamlit as st
import plotly.graph_objects as go
from services.api_service import api_service
from utils.auth import init_auth_state, require_auth
from utils.ui_helpers import (
    init_page_config,
    apply_custom_css,
    show_error,
    show_success,
    show_loading,
    show_toast,
)

# Initialize
init_page_config("Preferences | News Summarizer", "")
apply_custom_css()
init_auth_state()


@require_auth
def main() -> None:
    """User preferences management"""
    st.title("Preferences")
    st.caption("Customize your news feed and recommendation settings")

    st.divider()

    with show_loading("Loading your preferences..."):
        result = api_service.get_preferences()

    if not result["success"]:
        show_error(f"Failed to load preferences: {result.get('error')}")
        return

    preferences = result["data"]
    learned_topics = preferences.get("learned_preferences", {})

    tab1, tab2, tab3 = st.tabs(["Topic Preferences", "Learned Interests", "Settings"])

    # ====================================================================
    # TOPIC PREFERENCES
    # ====================================================================
    with tab1:
        st.markdown("### Select Your Interests")
        st.caption("Choose topics you want to see more of in your feed")

        topic_categories = {
            "News & Current Affairs": ["World News", "Politics", "Business", "Economy"],
            "Technology & Science": ["Technology", "Science", "AI & Machine Learning", "Space"],
            "Lifestyle": ["Entertainment", "Sports", "Health", "Travel"],
            "Other": ["Education", "Environment", "Culture", "Opinion"],
        }

        user_topics = preferences.get("favorite_topics", [])

        with st.form("preferences_form"):
            selected_topics = []

            for category, topics in topic_categories.items():
                st.markdown(f"**{category}**")
                cols = st.columns(4)
                for idx, topic in enumerate(topics):
                    with cols[idx % 4]:
                        if st.checkbox(topic, value=topic in user_topics, key=f"topic_{topic}"):
                            selected_topics.append(topic)

            st.divider()

            st.markdown("### Feed Settings")

            col1, col2 = st.columns(2)

            with col1:
                exploration_level = st.slider(
                    "Exploration vs Personalization",
                    min_value=0,
                    max_value=100,
                    value=preferences.get("exploration_level", 50),
                    help="0 = Only show similar articles, 100 = Show diverse content",
                )

            with col2:
                articles_per_page = st.number_input(
                    "Articles per page",
                    min_value=5,
                    max_value=50,
                    value=preferences.get("articles_per_page", 10),
                    step=5,
                )

            if st.form_submit_button("Save Preferences", use_container_width=True, type="primary"):
                updated_prefs = {
                    "favorite_topics": selected_topics,
                    "exploration_level": exploration_level,
                    "articles_per_page": articles_per_page,
                }

                with show_loading("Saving preferences..."):
                    update_result = api_service.update_preferences(updated_prefs)

                if update_result["success"]:
                    show_success("Preferences saved successfully!")
                    show_toast("Your feed will be updated!")
                else:
                    show_error(f"Failed to save: {update_result.get('error')}")

    # ====================================================================
    # LEARNED INTERESTS
    # ====================================================================
    with tab2:
        st.markdown("### What We've Learned About You")
        st.caption("These are topics inferred from your reading behavior")

        if learned_topics:
            topics = list(learned_topics.keys())
            scores = list(learned_topics.values())

            sorted_pairs = sorted(zip(topics, scores), key=lambda x: x[1], reverse=True)
            topics, scores = zip(*sorted_pairs)

            fig = go.Figure(
                data=[
                    go.Bar(
                        x=list(topics),
                        y=list(scores),
                        marker_color="lightblue",
                        text=[f"{s:.2%}" for s in scores],
                        textposition="auto",
                    )
                ]
            )

            fig.update_layout(
                title="Your Topic Interest Scores",
                xaxis_title="Topics",
                yaxis_title="Interest Score",
                yaxis=dict(range=[0, 1]),
                height=400,
            )

            st.plotly_chart(fig, use_container_width=True)

            st.markdown("#### Your Top Interests")
            cols = st.columns(3)
            for idx, (topic, score) in enumerate(list(sorted_pairs)[:6]):
                with cols[idx % 3]:
                    st.metric(topic, f"{score:.1%}")

            st.divider()

            if st.button("Reset Learned Preferences"):
                st.warning("This will clear all learned preferences. Your manual selections will remain.")
                if st.button("Confirm Reset", type="primary"):
                    show_success("Learned preferences reset! Start fresh.")
        else:
            st.info(
                "No learned preferences yet. Start reading articles to help us understand your interests!"
            )

    # ====================================================================
    # SETTINGS
    # ====================================================================
    with tab3:
        st.markdown("### Notification & Display Settings")

        col1, col2 = st.columns(2)

        with col1:
            st.markdown("#### Display Preferences")
            show_images = st.checkbox("Show article images", value=True)
            show_summaries = st.checkbox("Show summaries by default", value=True)
            compact_view = st.checkbox("Use compact view", value=False)
            dark_mode = st.checkbox("Dark mode (coming soon)", value=False, disabled=True)

        with col2:
            st.markdown("#### Content Filters")
            hide_read = st.checkbox("Hide already read articles", value=False)
            filter_duplicates = st.checkbox("Filter duplicate content", value=True)
            min_quality = st.slider("Minimum article quality", 0, 100, 50)

        st.divider()

        st.markdown("### Privacy Settings")

        col1, col2 = st.columns(2)

        with col1:
            enable_tracking = st.checkbox(
                "Enable reading analytics",
                value=True,
                help="Allow tracking to improve recommendations",
            )
            share_data = st.checkbox(
                "Share anonymized data",
                value=False,
                help="Help improve the platform",
            )

        with col2:
            personalization = st.checkbox(
                "Enable personalization",
                value=True,
                help="Use your reading history for recommendations",
            )

        st.divider()

        if st.button("Save Settings", use_container_width=True, type="primary"):
            show_success("Settings saved successfully!")

    st.divider()

    st.markdown("### Quick Actions")

    col1, col2, col3 = st.columns(3)

    with col1:
        if st.button("Refresh Feed", use_container_width=True):
            show_toast("Feed refreshed!")

    with col2:
        if st.button("View Analytics", use_container_width=True):
            st.info("Analytics feature coming soon!")

    with col3:
        if st.button("Export Data", use_container_width=True):
            st.info("Data export feature coming soon!")


if __name__ == "__main__":
    main()
