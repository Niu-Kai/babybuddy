"""Bound list responses while keeping existing limit/offset links compatible."""

from rest_framework.pagination import LimitOffsetPagination


class BoundedLimitOffsetPagination(LimitOffsetPagination):
    max_limit = 1000
