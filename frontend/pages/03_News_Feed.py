import time
import streamlit as st
from services.api_service import api_service
from utils.auth import init_auth_state, require_auth, logout
from utils.ui_helpers import (
    init_page_config,
    apply_custom_css,
    render_contact_developer_option,
    show_article_card,
    show_error,
    show_loading,
    show_toast,
)
from frontend_config import config

# Initialize
init_page_config("News Feed | News Central", "")
apply_custom_css()
init_auth_state()

# Initialize session state for feed
st.session_state.setdefault("feed_page", 1)
st.session_state.setdefault("feed_articles", [])
st.session_state.setdefault("selected_topics", [])
st.session_state.setdefault("feed_type", "personalized")
st.session_state.setdefault("rss_synced_topics_key", "")


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


AVAILABLE_TOPICS = [
    "Technology",
    "Science",
    "Business",
    "Politics",
    "Sports",
    "Entertainment",
    "Health",
    "World",
]


@require_auth
def main() -> None:
    """Main news feed"""

    # ── Sidebar (minimal: user info + feed type) ──
    with st.sidebar:
        st.markdown(f":material/person: Logged in as **{st.session_state.get('username', 'User')}**")
        if st.button(":material/logout: Logout", use_container_width=True):
            logout()
        render_contact_developer_option()

        st.divider()
        st.markdown("### :material/tune: Feed Mode")

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
                "latest": ":material/breaking_news: Latest News",
                "personalized": ":material/recommend: Personalized",
                "search": ":material/search: Search",
            }[x],
            key="feed_type_selector",
        )

        if feed_type != st.session_state.feed_type:
            st.session_state.feed_type = feed_type
            st.session_state.feed_page = 1
            st.session_state.feed_articles = []
            st.rerun()

    # ── Header ──
    col1, col2 = st.columns([3, 1])
    with col1:
        st.title(":material/newspaper: Your News Feed")
        st.caption(f"Welcome back, **{st.session_state.get('username', 'User')}**!")

    with col2:
        if st.button(":material/refresh: Refresh", use_container_width=True):
            st.session_state.feed_page = 1
            st.session_state.feed_articles = []
            st.rerun()

    # ── Inline filters (search bar + topics) ──
    if st.session_state.feed_type == "search":
        _render_search_bar()
    elif st.session_state.feed_type in ("latest", "personalized"):
        _render_topic_filter()

    st.divider()

    # ── Main content ──
    if st.session_state.feed_type == "personalized":
        show_personalized_feed()
    elif st.session_state.feed_type == "latest":
        show_latest_feed()
    else:
        show_search_results()


# ─── Inline filter components ───────────────────────────────────────────────


def _render_search_bar() -> None:
    """Search box rendered in the main content area."""
    col_input, col_btn = st.columns([4, 1])
    with col_input:
        search_query = st.text_input(
            "Search news",
            placeholder="Enter keywords...",
            key="search_query",
            icon=":material/search:",
            label_visibility="collapsed",
        )
    with col_btn:
        search_clicked = st.button(
            ":material/search: Search",
            use_container_width=True,
            type="primary",
        )

    if search_clicked and search_query:
        st.session_state.search_query_active = search_query
        st.session_state.feed_page = 1
        st.session_state.feed_articles = []
        st.rerun()


def _render_topic_filter() -> None:
    """Topic multiselect rendered in the main content area."""
    selected_topics = st.multiselect(
        ":material/label: Filter by Topics",
        AVAILABLE_TOPICS,
        default=st.session_state.selected_topics,
        key="topic_filter_inline",
    )

    if selected_topics != st.session_state.selected_topics:
        st.session_state.selected_topics = selected_topics
        st.session_state.feed_page = 1
        st.session_state.feed_articles = []
        st.rerun()


def show_personalized_feed() -> None:
    """Display personalized recommendations"""
    st.markdown("### :material/recommend: Recommended for You")
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
        st.info(":material/lightbulb: No recommendations yet — start reading articles and giving feedback to unlock personalized suggestions!")


def show_latest_feed() -> None:
    """Display latest news"""
    st.markdown("### :material/breaking_news: Latest News")
    st.caption("Fresh articles from all sources")

    topics = [t.lower() for t in st.session_state.selected_topics]
    topic_key = ",".join(sorted(set(topics))) if topics else ""
    if not topic_key:
        st.session_state.rss_synced_topics_key = ""

    # Sync topic-specific RSS feeds once whenever topic selection changes.
    if topic_key and topic_key != st.session_state.get("rss_synced_topics_key", ""):
        with show_loading("Fetching RSS feeds for selected topics..."):
            sync_result = api_service.trigger_news_fetch(
                queries=topics,
                sources=["rss"],
                limit=max(config.ARTICLES_PER_PAGE * 2, 20),
            )

            if sync_result["success"]:
                task_id = sync_result["data"].get("task_id")
                if task_id:
                    for _ in range(20):
                        status_result = api_service.get_task_status(task_id)
                        if not status_result["success"]:
                            break
                        task_status = status_result.get("data", {}).get("status")
                        if task_status in {"SUCCESS", "FAILURE", "REVOKED"}:
                            break
                        time.sleep(1)
            else:
                show_error(f"Failed to fetch topic RSS feeds: {sync_result.get('error')}")

        st.session_state.rss_synced_topics_key = topic_key
        st.session_state.feed_page = 1
        st.session_state.feed_articles = []

    if not st.session_state.feed_articles or st.session_state.feed_page == 1:
        with show_loading("Loading latest news..."):
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
        st.info(":material/inbox: No articles match these filters. Try broadening your topic selection.")

def show_search_results() -> None:
    """Display search results with filters, facets, and suggestions."""
    query = st.session_state.get("search_query_active", "")

    if not query:
        st.info(":material/search: Type a query above and press Search to find articles.")
        return

    st.markdown(f"### :material/search: Results for \u201c{query}\u201d")

    # ── Search filters row ──
    f1, f2, f3, f4 = st.columns([2, 3, 2, 2])
    with f1:
        sort_by = st.selectbox(
            "Sort by",
            ["relevance", "date", "popularity"],
            format_func=lambda x: {
                "relevance": "Relevance",
                "date": "Most Recent",
                "popularity": "Most Popular",
            }[x],
            key="search_sort_by",
        )
    with f2:
        search_topics = st.multiselect(
            "Filter topics",
            AVAILABLE_TOPICS,
            default=st.session_state.get("_search_topics", []),
            key="search_topics_filter",
        )
        # persist so we can detect changes
        if search_topics != st.session_state.get("_search_topics", []):
            st.session_state._search_topics = search_topics
    with f3:
        from_date = st.date_input("From", value=None, key="search_from_date")
    with f4:
        to_date = st.date_input("To", value=None, key="search_to_date")

    # Determine whether filters changed → re-fetch
    filter_key = f"{sort_by}|{','.join(search_topics)}|{from_date}|{to_date}"
    if filter_key != st.session_state.get("_search_filter_key", ""):
        st.session_state._search_filter_key = filter_key
        st.session_state.feed_page = 1
        st.session_state.feed_articles = []

    topics_lower = [t.lower() for t in search_topics] if search_topics else None

    if not st.session_state.feed_articles or st.session_state.feed_page == 1:
        from_str = from_date.isoformat() if from_date else None
        to_str = to_date.isoformat() if to_date else None

        with show_loading(f"Searching for \u201c{query}\u201d..."):
            result = api_service.search_news(
                query=query,
                page=st.session_state.feed_page,
                limit=config.ARTICLES_PER_PAGE,
                sort_by=sort_by,
                topics=topics_lower,
                from_date=from_str,
                to_date=to_str,
            )

        if result["success"]:
            data = result.get("data", {})
            # Backend returns "results" (not "articles")
            articles = data.get("results", data.get("articles", []))
            st.session_state._search_total = data.get("total", len(articles))
            st.session_state._search_suggestions = data.get("suggestions", [])
            st.session_state._search_facets = data.get("facets", {})
            if st.session_state.feed_page == 1:
                st.session_state.feed_articles = articles
            else:
                st.session_state.feed_articles.extend(articles)
        else:
            show_error(f"Search failed: {result.get('error')}")
            return

    total = st.session_state.get("_search_total", 0)
    facets = st.session_state.get("_search_facets", {})

    if st.session_state.feed_articles:
        st.caption(f"Showing {len(st.session_state.feed_articles)} of {total} results")

        # Show facets as badges if available
        topic_facets = facets.get("topics", {})
        if topic_facets:
            top_topics = sorted(topic_facets.items(), key=lambda x: x[1], reverse=True)[:6]
            facet_cols = st.columns(min(len(top_topics), 6) + 1, gap="small")
            for i, (topic, count) in enumerate(top_topics):
                with facet_cols[i]:
                    st.badge(f"{topic} ({count})", color="blue")

        for article in st.session_state.feed_articles:
            show_article_card(article, show_feedback=True)

        # Load more if there are more results
        if len(st.session_state.feed_articles) < total:
            col1, col2, col3 = st.columns([1, 1, 1])
            with col2:
                if st.button(":material/expand_more: Load More", use_container_width=True):
                    st.session_state.feed_page += 1
                    from_str = from_date.isoformat() if from_date else None
                    to_str = to_date.isoformat() if to_date else None

                    with show_loading("Loading more results..."):
                        result = api_service.search_news(
                            query=query,
                            page=st.session_state.feed_page,
                            limit=config.ARTICLES_PER_PAGE,
                            sort_by=sort_by,
                            topics=topics_lower,
                            from_date=from_str,
                            to_date=to_str,
                        )

                    if result["success"]:
                        data = result.get("data", {})
                        new_articles = data.get("results", data.get("articles", []))
                        st.session_state.feed_articles.extend(new_articles)
                        show_toast("Loaded more results!")
                        st.rerun()
    else:
        suggestions = st.session_state.get("_search_suggestions", [])
        if suggestions:
            st.warning(f":material/search_off: No results for \u201c{query}\u201d.")
            st.caption("**Suggestions:** " + " \u2022 ".join(suggestions))
        else:
            st.warning(f":material/search_off: No results for \u201c{query}\u201d. Try different keywords or broaden your query.")


if __name__ == "__main__":
    main()
