"""Cursor pagination for /api/v1/.

Cursor rather than offset because the consumer polls: with `?page=2` a ticket
updated mid-sync shifts every later row by one and the sync silently skips a
record. A cursor is anchored to a value, not a position.
"""
from rest_framework.pagination import CursorPagination


class TicketCursorPagination(CursorPagination):
    """Ordered by `updated_at` ASCENDING, with `pk` breaking ties.

    Ascending is the direction that makes an incremental sync correct. Paired
    with `updated_since` it is resumable and at-least-once: a row touched while
    the consumer is part-way through moves toward the END of the ordering, so
    it is seen again on this pass or the next. Under a descending order the
    same row moves behind the cursor and is lost until something else touches
    it. `pk` is appended so that rows sharing a timestamp still have one
    deterministic order rather than whatever the planner returns.
    """

    ordering = ('updated_at', 'pk')
    page_size = 100
    page_size_query_param = 'limit'
    max_page_size = 500
    cursor_query_param = 'cursor'


class CompanyCursorPagination(CursorPagination):
    """Companies are few and are read for discovery, so order by name."""

    ordering = ('name', 'pk')
    page_size = 200
    page_size_query_param = 'limit'
    max_page_size = 500
    cursor_query_param = 'cursor'
