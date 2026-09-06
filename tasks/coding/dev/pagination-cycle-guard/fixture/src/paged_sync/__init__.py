"""Public API for the paged synchronization fixture."""

from .errors import PageLimitExceeded, PaginationCycleError
from .models import Page, PageSource, Record
from .sync import collect_records

__all__ = [
    "Page",
    "PageLimitExceeded",
    "PageSource",
    "PaginationCycleError",
    "Record",
    "collect_records",
]
