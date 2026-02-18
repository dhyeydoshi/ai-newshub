from fastapi import APIRouter

api_router = APIRouter()


def include_routers():
    from app.api.auth import router as auth_router
    from app.api.articles import router as articles_router
    from app.api.user import router as user_router
    from app.api.feedback import router as feedback_router
    from app.api.analytics import router as analytics_router
    from app.api.recommendations import router as recommendations_router
    from app.api.news import router as news_router
    from app.api.integration_management import router as integration_management_router
    from app.api.integrations import router as integrations_router

    api_router.include_router(auth_router, tags=["Authentication"])
    api_router.include_router(articles_router,tags=["Articles"])
    api_router.include_router(user_router, tags=["Users"])
    api_router.include_router(feedback_router, tags=["Feedback"])
    api_router.include_router(analytics_router, tags=["Analytics"])
    api_router.include_router(recommendations_router, tags=["Recommendations"])
    api_router.include_router(news_router, tags=["News Aggregation"])
    api_router.include_router(integration_management_router, tags=["Integration Management"])
    api_router.include_router(integrations_router, tags=["Integration API"])

    return api_router

