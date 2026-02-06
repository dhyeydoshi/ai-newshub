from typing import Generic, TypeVar, List, Optional
from pydantic import BaseModel
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql import Select

T = TypeVar('T')


class PaginatedResponse(BaseModel, Generic[T]):
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
    return {
        'page': max(1, page),
        'page_size': min(page_size, max_page_size)
    }

