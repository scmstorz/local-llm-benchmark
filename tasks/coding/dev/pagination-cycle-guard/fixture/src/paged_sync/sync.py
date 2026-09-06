"""Collect records from a cursor-paginated source."""

from __future__ import annotations

from .errors import PageLimitExceeded
from .models import PageSource, Record


def collect_records(
    source: PageSource,
    *,
    start_cursor: str | None = None,
    max_pages: int = 100,
) -> list[Record]:
    """Return records from consecutive pages.

    The implementation intentionally contains the production-shaped regression
    described in the benchmark task.
    """
    if max_pages < 1:
        raise ValueError("max_pages must be at least one")

    records: list[Record] = []
    cursor = start_cursor
    for _ in range(max_pages):
        page = source.fetch_page(cursor)
        if not page.records:
            break
        records.extend(page.records)
        cursor = page.next_cursor
        if cursor is None:
            return records
    else:
        raise PageLimitExceeded(max_pages)

    return records
