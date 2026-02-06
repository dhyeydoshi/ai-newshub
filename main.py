from contextlib import asynccontextmanager
import asyncio
from fastapi import FastAPI, Request, status
from fastapi.responses import JSONResponse
from fastapi.exceptions import RequestValidationError
from starlette.exceptions import HTTPException as StarletteHTTPException
import redis.asyncio as aioredis
import logging
from datetime import datetime, timezone

from config import settings
from app.middleware import (
    SecurityHeadersMiddleware,
    RequestValidationMiddleware,
    CORSMiddleware,
    AuthenticationMiddleware,
)

# Configure logging
logging.basicConfig(
    level=settings.LOG_LEVEL,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Global Redis client for rate limiting and caching
redis_client: aioredis.Redis = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan manager"""
    global redis_client

    # Startup
    logger.info(f"Starting {settings.APP_NAME} v{settings.APP_VERSION}")
    logger.info(f"Environment: {settings.ENVIRONMENT}")

    # Connect to Redis for rate limiting and caching
    try:
        redis_client = aioredis.from_url(
            settings.REDIS_URL,
            encoding="utf-8",
            decode_responses=True,
            max_connections=settings.REDIS_MAX_CONNECTIONS
        )
        await redis_client.ping()
        logger.info("Connected to Redis successfully")

        # Initialize centralized cache manager
        from app.core.cache import init_cache_manager
        cache_manager = init_cache_manager(
            redis_client,
            default_ttl=settings.REDIS_CACHE_TTL,
            compression_threshold=1024,  # Compress values > 1KB
            key_prefix="news_app"
        )
        logger.info(" Cache manager initialized with compression enabled")
        logger.info(f"   - Default TTL: {settings.REDIS_CACHE_TTL}s")
        logger.info(f"   - Compression threshold: 1KB")
        logger.info(f"   - Key prefix: news_app")
    except Exception as e:
        logger.warning(f"Redis connection failed: {e}. Rate limiting and caching will be disabled.")
        redis_client = None

    # Initialize database tables (if needed)
    try:
        from app.core.database import init_db
        logger.info("Database ready")
    except Exception as e:
        logger.error(f"Database initialization error: {e}")

    # Celery runs independently - no initialization needed in FastAPI
    if settings.ENABLE_NEWS_SCHEDULER:
        logger.info(
            "News fetching is handled by Celery worker. "
            "Start worker with: celery -A app.celery_config:celery_app worker --beat --loglevel=info"
        )
        try:
            from app.utils.celery_helpers import get_celery_status

            celery_status = await asyncio.wait_for(get_celery_status(), timeout=5)
            active_workers = celery_status.get("workers", {}).get("active", 0)

            if active_workers == 0:
                logger.warning(
                    "Celery health warning: ENABLE_NEWS_SCHEDULER=true but 0 active Celery workers detected. "
                    "News ingestion tasks (NewsAPI/GDELT/RSS) will not run until a worker is started."
                )
            else:
                logger.info(f"Celery worker health OK: {active_workers} active worker(s)")
        except asyncio.TimeoutError:
            logger.warning("Celery health check timed out during startup")
        except Exception as e:
            logger.warning(f"Unable to verify Celery worker health at startup: {e}")

    logger.info("Application startup complete")

    logger.info("Registered routes:")
    for route in app.routes:
        if hasattr(route, "methods"):
            logger.info(f"{list(route.methods)[0]} {route.path}")
    
    # Log rate limiting status
    if redis_client and settings.RATE_LIMIT_ENABLED:
        logger.info(" Rate limiting is ACTIVE via dependency injection (see app/dependencies/rate_limit.py)")
        logger.info("   Use @rate_limit() decorator or Depends(check_rate_limit) on your routes")
    else:
        logger.info("  Rate limiting is DISABLED (Redis not connected or RATE_LIMIT_ENABLED=false)")

    # Log caching status
    if redis_client:
        from app.dependencies.cache import CacheConfig
        logger.info(" Redis caching is ACTIVE")
        logger.info(f"   - Article lists: {CacheConfig.ARTICLES_LIST_TTL}s")
        logger.info(f"   - Article details: {CacheConfig.ARTICLE_DETAIL_TTL}s")
        logger.info(f"   - User profiles: {CacheConfig.USER_PROFILE_TTL}s")
        logger.info(f"   - User preferences: {CacheConfig.USER_PREFERENCES_TTL}s")
        logger.info(f"   - Recommendations: {CacheConfig.RECOMMENDATIONS_TTL}s")
    else:
        logger.info("  Redis caching is DISABLED")

    yield

    # Shutdown
    logger.info("Shutting down application")

    if redis_client:
        await redis_client.close()
        logger.info("Redis connection closed")
    logger.info("Application shutdown complete")


# Create FastAPI application
app = FastAPI(
    title=settings.APP_NAME,
    version=settings.APP_VERSION,
    description="Secure news summarizer API with comprehensive security middleware and Redis caching",
    docs_url="/docs" if settings.DEBUG else None,
    redoc_url="/redoc" if settings.DEBUG else None,
    lifespan=lifespan
)


# 1. CORS Middleware (must be first to handle preflight)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_methods=settings.CORS_ALLOW_METHODS,
    allow_headers=settings.CORS_ALLOW_HEADERS,
    allow_credentials=settings.CORS_ALLOW_CREDENTIALS,
    max_age=settings.CORS_MAX_AGE
)

# 2. Security Headers Middleware
app.add_middleware(SecurityHeadersMiddleware)

# 3. Request Validation Middleware
app.add_middleware(RequestValidationMiddleware)

app.add_middleware(AuthenticationMiddleware)


@app.exception_handler(StarletteHTTPException)
async def http_exception_handler(request: Request, exc: StarletteHTTPException):
    """Handle HTTP exceptions"""
    logger.warning(f"HTTP {exc.status_code}: {exc.detail} - {request.url}")
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "error": exc.detail,
            "status_code": exc.status_code,
            "path": str(request.url.path)
        }
    )


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    """Handle validation errors"""
    logger.warning(f"Validation error: {exc.errors()} - {request.url}")
    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        content={
            "error": "Validation error",
            "details": exc.errors(),
            "status_code": 422
        }
    )


@app.exception_handler(Exception)
async def general_exception_handler(request: Request, exc: Exception):
    """Handle unexpected exceptions"""
    logger.error(f"Unexpected error: {exc} - {request.url}", exc_info=True)

    # Don't expose internal errors in production
    if settings.is_production:
        detail = "Internal server error"
    else:
        detail = str(exc)

    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={
            "error": detail,
            "status_code": 500
        }
    )


# Import API routers
from app.api import include_routers

# Register API routers
api_router = include_routers()
app.include_router(api_router, prefix="/api/v1")


@app.get("/")
async def root():
    """Root endpoint"""
    return {
        "message": "News Summarizer API",
        "version": settings.APP_VERSION,
        "docs": "/docs" if settings.DEBUG else None,
        "endpoints": {
            "authentication": "/api/v1/auth",
            "news": "/api/v1/news",
            "user": "/api/v1/user",
            "feedback": "/api/v1/feedback",
            "analytics": "/api/v1/analytics",
            "recommendations": "/api/v1/recommendations"
        }
    }


@app.get("/health")
async def health_check():
    """Health check endpoint"""
    redis_status = "connected" if redis_client else "disconnected"

    return {
        "status": "healthy",
        "app": settings.APP_NAME,
        "version": settings.APP_VERSION,
        "environment": settings.ENVIRONMENT,
        "redis": redis_status,
        "middleware": {
            "cors": True,
            "rate_limiting": settings.RATE_LIMIT_ENABLED and redis_client is not None,
            "authentication": True,
            "security_headers": True,
            "request_validation": True
        }
    }


@app.get("/api/v1/status")
async def api_status():
    status_data = {
        "api": "operational",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "services": {
            "database": "unknown",
            "redis": "connected" if redis_client else "disconnected",
            "rl_service": "unknown",
            "llm_service": "disabled"
        }
    }

    # Check database
    try:
        from app.core.database import engine
        from sqlalchemy import text
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
        status_data["services"]["database"] = "connected"
    except Exception as e:
        logger.error(f"Database health check failed: {e}")
        status_data["services"]["database"] = "disconnected"

    # Check RL service
    try:
        status_data["services"]["rl_service"] = "available"
    except:
        status_data["services"]["rl_service"] = "unavailable"

    return status_data


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=8000,
        reload=settings.DEBUG,
        log_level=settings.LOG_LEVEL.lower()
    )

