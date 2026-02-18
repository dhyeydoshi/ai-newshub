from typing import AsyncGenerator
from contextlib import asynccontextmanager
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker
from sqlalchemy.orm import declarative_base
from sqlalchemy.pool import NullPool
from sqlalchemy import text
import logging
import os

from config import settings

logger = logging.getLogger(__name__)

# Create declarative base
Base = declarative_base()


def _get_pool_config() -> dict:
    environment = (settings.ENVIRONMENT or "production").lower()

    if environment == "testing":
        return {"poolclass": NullPool}

    # Keep production concurrency higher than development, but configurable via env vars.
    if environment == "production":
        defaults = {
            "pool_size": 5,
            "max_overflow": 5,
            "pool_recycle": 900,
            "pool_timeout": 15,
        }
    else:
        defaults = {
            "pool_size": 20,
            "max_overflow": 30,
            "pool_recycle": 3600,
            "pool_timeout": 30,
        }

    return {
        "pool_size": int(os.getenv("DB_POOL_SIZE", str(defaults["pool_size"]))),
        "max_overflow": int(os.getenv("DB_MAX_OVERFLOW", str(defaults["max_overflow"]))),
        "pool_recycle": int(os.getenv("DB_POOL_RECYCLE", str(defaults["pool_recycle"]))),
        "pool_timeout": int(os.getenv("DB_POOL_TIMEOUT", str(defaults["pool_timeout"]))),
    }


_pool_config = _get_pool_config()
_engine_kwargs = {
    "echo": settings.DEBUG,
    "future": True,
    "pool_pre_ping": True,
}
_engine_kwargs.update(_pool_config)

engine = create_async_engine(settings.DATABASE_URL, **_engine_kwargs)

# Create async session factory
AsyncSessionLocal = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autocommit=False,
    autoflush=False
)


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    async with AsyncSessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()


async def check_database_connection() -> bool:
    """Verify database connectivity without mutating schema at runtime."""
    try:
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
        return True
    except Exception as e:
        logger.error(f"Database connectivity check failed: {e}")
        return False


async def has_alembic_version_table() -> bool:
    """Check whether Alembic version tracking table exists."""
    try:
        async with engine.connect() as conn:
            result = await conn.execute(text("SELECT to_regclass('public.alembic_version')"))
            table_name = result.scalar()
        return bool(table_name)
    except Exception as e:
        logger.warning(f"Failed to check Alembic version table: {e}")
        return False


async def close_db():
    await engine.dispose()
    logger.info("Database connections closed")


@asynccontextmanager
async def create_task_session():
    task_engine = create_async_engine(
        settings.DATABASE_URL,
        echo=settings.DEBUG,
        future=True,
        poolclass=NullPool,
    )
    factory = async_sessionmaker(
        task_engine,
        class_=AsyncSession,
        expire_on_commit=False,
        autocommit=False,
        autoflush=False,
    )
    try:
        async with factory() as session:
            yield session
    finally:
        await task_engine.dispose()


# Synchronous session for non-async code (e.g., Alembic migrations)
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

sync_engine = create_engine(
    settings.database_url_sync,
    echo=settings.DEBUG,
    pool_pre_ping=True
)

SessionLocal = sessionmaker(
    autocommit=False,
    autoflush=False,
    bind=sync_engine
)


def get_sync_db():
    """Get synchronous database session"""
    db = SessionLocal()
    try:
        yield db
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()
