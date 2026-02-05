import streamlit as st
from services.api_service import api_service
from utils.auth import init_auth_state, require_auth, logout
from utils.ui_helpers import (
    init_page_config,
    apply_custom_css,
    show_article_card,
    show_error,
    show_loading,
    show_toast,
)
from frontend_config import config

# Initialize
init_page_config("News Feed | News Summarizer", "")
apply_custom_css()
init_auth_state()

# Initialize session state for feed
st.session_state.setdefault("feed_page", 1)
st.session_state.setdefault("feed_articles", [])
st.session_state.setdefault("selected_topics", [])
st.session_state.setdefault("feed_type", "personalized")


def _extract_recommendations(data):
    """Normalize recommendations response from backend."""
    if isinstance(data, list):
        return data
    if isinstance(data, dict):
        recommendations = data.get("recommendations")
        if isinstance(recommendations, list):
            return recommendations
        articles = data.get("articles")
        if isinstance(articles, list):
            return articles
    return []


@require_auth
def main() -> None:
    """Main news feed"""

    # Header
    col1, col2 = st.columns([3, 1])
    with col1:
        st.title("Your News Feed")
        st.caption(f"Welcome back, **{st.session_state.get('username', 'User')}**!")

    with col2:
        if st.button("Refresh", use_container_width=True):
            st.session_state.feed_page = 1
            st.session_state.feed_articles = []
            st.rerun()

    st.divider()

    # Sidebar filters
    with st.sidebar:
        st.markdown(f"Logged in as **{st.session_state.get('username', 'User')}**")
        if st.button("Logout", use_container_width=True):
            logout()

        st.divider()
        st.markdown("### Feed Settings")

        # Feed type selector
        feed_options = ["latest", "personalized", "search"]
        if st.session_state.feed_type in feed_options:
            default_index = feed_options.index(st.session_state.feed_type)
        else:
            default_index = 0
        feed_type = st.radio(
            "Feed Type",
            feed_options,
            index=default_index,
            format_func=lambda x: {
                "latest": "Latest News",
                "personalized": "Personalized",
                "search": "Search",
            }[x],
            key="feed_type_selector",
        )

        if feed_type != st.session_state.feed_type:
            st.session_state.feed_type = feed_type
            st.session_state.feed_page = 1
            st.session_state.feed_articles = []
            st.rerun()

        st.divider()

        # Topic filters
        if feed_type in ["personalized", "latest"]:
            st.markdown("#### Filter by Topics")

            available_topics = [
                "Technology",
                "Science",
                "Business",
                "Politics",
                "Sports",
                "Entertainment",
                "Health",
                "World",
            ]

            selected_topics = st.multiselect(
                "Select topics",
                available_topics,
                default=st.session_state.selected_topics,
                help="Filter articles by topics",
            )

            if selected_topics != st.session_state.selected_topics:
                st.session_state.selected_topics = selected_topics
                st.session_state.feed_page = 1
                st.session_state.feed_articles = []
                st.rerun()

        # Search box
        elif feed_type == "search":
            st.markdown("#### Search News")
            search_query = st.text_input(
                "Search query",
                placeholder="Enter keywords...",
                key="search_query",
            )

            if st.button("Search", use_container_width=True, type="primary"):
                if search_query:
                    st.session_state.search_query_active = search_query
                    st.session_state.feed_page = 1
                    st.session_state.feed_articles = []
                    st.rerun()

        st.divider()

        # Quick stats
        st.markdown("#### Your Stats")
        col1, col2 = st.columns(2)
        with col1:
            st.metric("Articles Read", "42")
        with col2:
            st.metric("This Week", "+12")

    # Main content area
    if st.session_state.feed_type == "personalized":
        show_personalized_feed()
    elif st.session_state.feed_type == "latest":
        show_latest_feed()
    else:
        show_search_results()


def show_personalized_feed() -> None:
    """Display personalized recommendations"""
    st.markdown("### Recommended for You")
    st.caption("Articles selected based on your reading preferences")

    if not st.session_state.feed_articles:
        with show_loading("Loading personalized recommendations..."):
            result = api_service.get_recommendations(limit=config.ARTICLES_PER_PAGE)

        if result["success"]:
            st.session_state.feed_articles = _extract_recommendations(result["data"])
        else:
            show_error(f"Failed to load recommendations: {result.get('error')}")
            return

    if st.session_state.feed_articles:
        for article in st.session_state.feed_articles:
            show_article_card(article.get("article", article), show_feedback=True)

        col1, col2, col3 = st.columns([1, 1, 1])
        with col2:
            if st.button("Load More", use_container_width=True):
                with show_loading("Loading more articles..."):
                    result = api_service.get_recommendations(limit=config.ARTICLES_PER_PAGE)

                if result["success"]:
                    new_articles = _extract_recommendations(result["data"])
                    st.session_state.feed_articles.extend(new_articles)
                    show_toast("Loaded more articles!")
                    st.rerun()
    else:
        st.info("No recommendations available yet. Start reading articles to get personalized suggestions!")


def show_latest_feed() -> None:
    """Display latest news"""
    st.markdown("### Latest News")
    st.caption("Fresh articles from all sources")

    if not st.session_state.feed_articles or st.session_state.feed_page == 1:
        with show_loading("Loading latest news..."):
            topics = [t.lower() for t in st.session_state.selected_topics]
            result = api_service.get_latest_news(
                page=st.session_state.feed_page,
                limit=config.ARTICLES_PER_PAGE,
                topics=topics if topics else None,
            )

        if result["success"]:
            articles = result["data"].get("articles", [])
            if st.session_state.feed_page == 1:
                st.session_state.feed_articles = articles
            else:
                st.session_state.feed_articles.extend(articles)
        else:
            show_error(f"Failed to load news: {result.get('error')}")
            return

    if st.session_state.feed_articles:
        for article in st.session_state.feed_articles:
            show_article_card(article, show_feedback=True)

        col1, col2, col3 = st.columns([1, 1, 1])
        with col2:
            if st.button("Load More", use_container_width=True):
                st.session_state.feed_page += 1
                with show_loading("Loading more articles..."):
                    topics = [t.lower() for t in st.session_state.selected_topics]
                    result = api_service.get_latest_news(
                        page=st.session_state.feed_page,
                        limit=config.ARTICLES_PER_PAGE,
                        topics=topics if topics else None,
                    )

                if result["success"]:
                    new_articles = result["data"].get("articles", [])
                    st.session_state.feed_articles.extend(new_articles)
                    show_toast("Loaded more articles!")
                    st.rerun()
    else:
        st.info("No articles available")


def show_search_results() -> None:
    """Display search results"""
    query = st.session_state.get("search_query_active", "")

    if not query:
        st.info("Enter a search query in the sidebar to find articles")
        return

    st.markdown(f"### Search Results for '{query}'")

    if not st.session_state.feed_articles or st.session_state.feed_page == 1:
        with show_loading(f"Searching for '{query}'..."):
            result = api_service.search_news(
                query=query,
                page=st.session_state.feed_page,
                limit=config.ARTICLES_PER_PAGE,
            )

        if result["success"]:
            articles = result["data"].get("articles", [])
            if st.session_state.feed_page == 1:
                st.session_state.feed_articles = articles
            else:
                st.session_state.feed_articles.extend(articles)
        else:
            show_error(f"Search failed: {result.get('error')}")
            return

    if st.session_state.feed_articles:
        st.caption(f"Found {len(st.session_state.feed_articles)} results")

        for article in st.session_state.feed_articles:
            show_article_card(article, show_feedback=True)

        col1, col2, col3 = st.columns([1, 1, 1])
        with col2:
            if st.button("Load More", use_container_width=True):
                st.session_state.feed_page += 1
                with show_loading("Loading more results..."):
                    result = api_service.search_news(
                        query=query,
                        page=st.session_state.feed_page,
                        limit=config.ARTICLES_PER_PAGE,
                    )

                if result["success"]:
                    new_articles = result["data"].get("articles", [])
                    st.session_state.feed_articles.extend(new_articles)
                    show_toast("Loaded more results!")
                    st.rerun()
    else:
        st.warning(f"No results found for '{query}'. Try different keywords.")


if __name__ == "__main__":
    main()
