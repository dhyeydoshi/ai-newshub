from app.schemas.auth import (
    UserRegister,
    UserLogin,
    TokenRefresh,
    PasswordResetRequest,
    PasswordReset,
    PasswordChange,
    EmailVerification,
    ResendVerification,
    UserResponse,
    LoginResponse,
    TokenResponse,
    MessageResponse,
    UserDetailResponse,
    SessionResponse
)
from app.schemas.raw_article import RawArticle
from app.schemas.article import (
    ArticleResponse,
    ArticleListResponse,
    ArticleDetailResponse,
    SummaryRequest,
    SummaryResponse,
    NewsQuery,
    TrendingArticlesResponse,
    SearchResultsResponse,
    PersonalizedFeedRequest,
    PersonalizedFeedResponse
)
from app.schemas.user import (
    UserProfileResponse,
    UserProfileUpdate,
    UserPreferencesResponse,
    UserPreferencesUpdate,
    UserEngagementStats,
    ReadingHistoryResponse,
    ReadingHistoryItem,
    AccountDeletionRequest,
    DataExportRequest,
    DataExportResponse
)
from app.schemas.feedback import (
    ArticleFeedbackRequest,
    SummaryFeedbackRequest,
    FeedbackResponse,
    ReadingInteractionRequest,
    InteractionResponse,
    EngagementMetrics,
    UserEngagementAnalytics,
    EngagementAnalyticsResponse
)

__all__ = [
    # Auth schemas
    "UserRegister",
    "UserLogin",
    "TokenRefresh",
    "PasswordResetRequest",
    "PasswordReset",
    "PasswordChange",
    "EmailVerification",
    "ResendVerification",
    "UserResponse",
    "LoginResponse",
    "TokenResponse",
    "MessageResponse",
    "UserDetailResponse",
    "SessionResponse",
    # Article schemas
    "ArticleResponse",
    "ArticleListResponse",
    "ArticleDetailResponse",
    "SummaryRequest",
    "SummaryResponse",
    "NewsQuery",
    "TrendingArticlesResponse",
    "SearchResultsResponse",
    "PersonalizedFeedRequest",
    "PersonalizedFeedResponse",
    # User schemas
    "UserProfileResponse",
    "UserProfileUpdate",
    "UserPreferencesResponse",
    "UserPreferencesUpdate",
    "UserEngagementStats",
    "ReadingHistoryResponse",
    "ReadingHistoryItem",
    "AccountDeletionRequest",
    "DataExportRequest",
    "DataExportResponse",
    # Feedback schemas
    "ArticleFeedbackRequest",
    "SummaryFeedbackRequest",
    "FeedbackResponse",
    "ReadingInteractionRequest",
    "InteractionResponse",
    "EngagementMetrics",
    "UserEngagementAnalytics",
    "EngagementAnalyticsResponse"
]
