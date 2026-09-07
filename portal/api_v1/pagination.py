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


class ShareEventCursorPagination(CursorPagination):
    """Same ascending contract as tickets, for the same reason.

    It matters more here, because a share event's interesting moments nearly
    all arrive AFTER the row is created: the push is the boring half, and the
    open — days later — is the half a health dashboard is actually waiting for.
    Ordering on `sent_at` would leave every one of those changes behind a
    consumer's cursor, so `ShareNotice.updated_at` exists specifically to give
    this ordering something that moves. See the comment on that field.
    """

    ordering = ('updated_at', 'pk')
    page_size = 100
    page_size_query_param = 'limit'
    max_page_size = 500
    cursor_query_param = 'cursor'
