"""Services package"""
from app.services.rl_service import rl_service, RLRecommendationService
from app.services.news_aggregator import (
    NewsAggregatorService,
    get_news_aggregator,
    ArticleDeduplicator
)
from app.services.article_persistence import (
    ArticlePersistenceService,
    article_persistence_service
)
from app.services.news_ingestion_service import (
    NewsIngestionService,
    news_ingestion_service
)

__all__ = [
    'rl_service',
    'RLRecommendationService',
    'NewsAggregatorService',
    'get_news_aggregator',
    'ArticleDeduplicator',
    'ArticlePersistenceService',
    'article_persistence_service',
    'NewsIngestionService',
    'news_ingestion_service'
]
