"""Pagination.

Cursor pagination is the default because prospect and message tables grow to
millions of rows per tenant and ``OFFSET`` degrades badly there, and because
rows arrive continuously -- offset paging would show duplicates and skip
records while a campaign is running.
"""

from __future__ import annotations

from collections import OrderedDict
from collections.abc import Sequence
from typing import Any

from rest_framework import pagination
from rest_framework.response import Response


class CursorPagination(pagination.CursorPagination):
    page_size = 25
    page_size_query_param = "page_size"
    max_page_size = 200
    # Stable, indexed ordering. Rows created in the same millisecond would
    # otherwise be ordered non-deterministically and could be skipped.
    ordering = ("-created_at", "-id")

    def get_paginated_response(self, data: Sequence[Any]) -> Response:
        return Response(
            OrderedDict(
                [
                    ("next", self.get_next_link()),
                    ("previous", self.get_previous_link()),
                    ("page_size", self.get_page_size(self.request) or self.page_size),
                    ("results", data),
                ]
            )
        )


class PageNumberPagination(pagination.PageNumberPagination):
    """For small, bounded collections where a total count is genuinely useful."""

    page_size = 25
    page_size_query_param = "page_size"
    max_page_size = 200

    def get_paginated_response(self, data: Sequence[Any]) -> Response:
        return Response(
            OrderedDict(
                [
                    ("count", self.page.paginator.count),
                    ("next", self.get_next_link()),
                    ("previous", self.get_previous_link()),
                    ("results", data),
                ]
            )
        )
