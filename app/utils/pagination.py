"""
Pagination Utilities for FastAPI
Provides cursor-based and offset-based pagination helpers
"""
from typing import Generic, TypeVar, List, Optional
from pydantic import BaseModel
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql import Select

T = TypeVar('T')


class PaginatedResponse(BaseModel, Generic[T]):
    """
    Generic paginated response model

    Usage:
        response = PaginatedResponse[ArticleResponse](
            items=articles,
            total=100,
            page=1,
            page_size=20,
            has_next=True,
            has_prev=False
        )
    """
    items: List[T]
    total: int
    page: int
    page_size: int
    has_next: bool
    has_prev: bool
    total_pages: int

    class Config:
        arbitrary_types_allowed = True


class CursorPaginatedResponse(BaseModel, Generic[T]):
    """
    Cursor-based paginated response (more efficient for large datasets)

    Advantages over offset pagination:
    - Consistent results even when data changes
    - Better performance for large offsets
    - No "page drift" issues
    """
    items: List[T]
    next_cursor: Optional[str] = None
    prev_cursor: Optional[str] = None
    has_next: bool
    has_prev: bool

    class Config:
        arbitrary_types_allowed = True


async def paginate_offset(
    db: AsyncSession,
    query: Select,
    page: int = 1,
    page_size: int = 20,
    max_page_size: int = 100
) -> dict:
    """
    Offset-based pagination helper

    Args:
        db: Database session
        query: SQLAlchemy select query
        page: Page number (1-indexed)
        page_size: Items per page
        max_page_size: Maximum allowed page size

    Returns:
        Dictionary with items, total, and pagination metadata

    Example:
        query = select(Article).where(Article.is_active == True)
        result = await paginate_offset(db, query, page=1, page_size=20)

        return PaginatedResponse[ArticleResponse](
            items=[ArticleResponse.from_orm(item) for item in result['items']],
            **result['meta']
        )
    """
    # Validate and constrain page_size
    page_size = min(page_size, max_page_size)
    page = max(1, page)  # Ensure page is at least 1

    # Count total items
    count_query = select(func.count()).select_from(query.subquery())
    total = await db.scalar(count_query) or 0

    # Calculate pagination
    total_pages = (total + page_size - 1) // page_size if total > 0 else 1
    offset = (page - 1) * page_size

    # Get items for current page
    paginated_query = query.offset(offset).limit(page_size)
    result = await db.execute(paginated_query)
    items = result.scalars().all()

    return {
        'items': items,
        'meta': {
            'total': total,
            'page': page,
            'page_size': page_size,
            'has_next': page < total_pages,
            'has_prev': page > 1,
            'total_pages': total_pages
        }
    }


async def paginate_cursor(
    db: AsyncSession,
    query: Select,
    cursor_field: str,
    cursor: Optional[str] = None,
    page_size: int = 20,
    direction: str = 'next'
) -> dict:
    """
    Cursor-based pagination helper (more efficient for large datasets)

    Args:
        db: Database session
        query: SQLAlchemy select query
        cursor_field: Field name to use as cursor (usually 'id' or 'created_at')
        cursor: Current cursor value
        page_size: Items per page
        direction: 'next' or 'prev'

    Returns:
        Dictionary with items and cursor metadata

    Example:
        query = select(Article).order_by(Article.created_at.desc())
        result = await paginate_cursor(
            db,
            query,
            cursor_field='created_at',
            cursor=request.query_params.get('cursor'),
            page_size=20
        )
    """
    # Get one extra item to determine if there's a next page
    limit = page_size + 1

    # Apply cursor filter if provided
    if cursor:
        if direction == 'next':
            query = query.where(getattr(query.column_descriptions[0]['entity'], cursor_field) < cursor)
        else:
            query = query.where(getattr(query.column_descriptions[0]['entity'], cursor_field) > cursor)

    # Execute query
    result = await db.execute(query.limit(limit))
    items = result.scalars().all()

    # Check if there are more items
    has_more = len(items) > page_size
    if has_more:
        items = items[:page_size]

    # Get cursors
    next_cursor = None
    prev_cursor = None

    if items:
        if direction == 'next' and has_more:
            next_cursor = str(getattr(items[-1], cursor_field))
        if direction == 'prev' or cursor:
            prev_cursor = str(getattr(items[0], cursor_field))

    return {
        'items': items,
        'meta': {
            'next_cursor': next_cursor,
            'prev_cursor': prev_cursor,
            'has_next': has_more if direction == 'next' else None,
            'has_prev': bool(cursor)
        }
    }


# Helper function for FastAPI route
def create_pagination_params(
    page: int = 1,
    page_size: int = 20,
    max_page_size: int = 100
):
    """
    Dependency for pagination query parameters

    Usage in FastAPI:
        from fastapi import Depends

        @router.get("/articles")
        async def list_articles(
            pagination = Depends(create_pagination_params)
        ):
            query = select(Article)
            result = await paginate_offset(db, query, **pagination)
            return result
    """
    return {
        'page': max(1, page),
        'page_size': min(page_size, max_page_size)
    }

