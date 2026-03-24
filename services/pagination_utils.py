from math import ceil
from typing import Optional


DEFAULT_PAGE = 1
DEFAULT_PAGE_SIZE = 12
MAX_PAGE_SIZE = 100


def normalize_pagination(page: Optional[int], page_size: Optional[int], *, default_page_size: int = DEFAULT_PAGE_SIZE) -> tuple[Optional[int], Optional[int]]:
    if page is None and page_size is None:
        return None, None

    resolved_page = max(int(page or DEFAULT_PAGE), 1)
    resolved_page_size = max(1, min(int(page_size or default_page_size), MAX_PAGE_SIZE))
    return resolved_page, resolved_page_size


def pagination_slice(page: int, page_size: int) -> tuple[int, int]:
    start = (page - 1) * page_size
    end = start + page_size
    return start, end


def build_pagination(total_items: int, page: Optional[int], page_size: Optional[int]) -> Optional[dict]:
    if page is None or page_size is None:
        return None

    total_pages = max(ceil(total_items / page_size), 1) if total_items else 1
    return {
        "page": page,
        "pageSize": page_size,
        "totalItems": total_items,
        "totalPages": total_pages,
        "hasNextPage": page < total_pages,
        "hasPreviousPage": page > 1,
    }
