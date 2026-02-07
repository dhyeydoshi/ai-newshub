from typing import AsyncGenerator
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker
from sqlalchemy.orm import declarative_base
from sqlalchemy.pool import NullPool
from sqlalchemy import text
import logging

from config import settings

logger = logging.getLogger(__name__)

# Create declarative base
Base = declarative_base()

engine = create_async_engine(
    settings.DATABASE_URL,
    echo=settings.DEBUG,
    future=True,
    pool_pre_ping=True,
    # For async engines, only use NullPool for testing, otherwise let SQLAlchemy choose the pool
    poolclass=NullPool if settings.ENVIRONMENT == "testing" else None,
    pool_size=20,  # Increased from 10 for better concurrency
    max_overflow=30,  # Increased from 20
    pool_recycle=3600,  # Recycle connections after 1 hour
    pool_timeout=30,  # Wait up to 30s for a connection
)

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
