from pathlib import Path
import re

import streamlit as st


_ROUTE_TO_PAGE = {
    "home": "Home.py",
    "login": "pages/02_Login.py",
    "news-feed": "pages/03_News_Feed.py",
    "article-view": "pages/04_Article_View.py",
    "preferences": "pages/05_Preferences.py",
    "profile": "pages/06_Profile.py",
    "integrations": "pages/07_Integrations.py",
}

_ROUTE_ALIASES = {
    "news": "news-feed",
    "newsfeed": "news-feed",
    "news_feed": "news-feed",
    "article": "article-view",
    "article_view": "article-view",
    "integration": "integrations",
    "settings": "preferences",
}


def _normalize_route_name(value: str) -> str:
    route = str(value or "").strip()
    if not route:
        return "home"
    if route in _ROUTE_TO_PAGE:
        return route
    if route in _ROUTE_ALIASES:
        return _ROUTE_ALIASES[route]

    stem = Path(route).stem
    stem = re.sub(r"^\d+[_-]*", "", stem)
    slug = re.sub(r"[\s_]+", "-", stem.strip().lower()).strip("-")

    if slug in _ROUTE_TO_PAGE:
        return slug
    if slug in _ROUTE_ALIASES:
        return _ROUTE_ALIASES[slug]
    raise ValueError(f"Unknown frontend route: {value}")


def switch_page(route: str) -> None:
    normalized = _normalize_route_name(route)
    page_path = _ROUTE_TO_PAGE[normalized]
    st.switch_page(page_path)

