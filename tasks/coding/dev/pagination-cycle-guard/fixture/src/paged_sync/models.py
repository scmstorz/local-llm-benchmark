"""Data types used by the paged synchronization fixture."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True)
class Record:
    """One logical record returned by the upstream source."""

    identifier: str
    payload: str


@dataclass(frozen=True)
class Page:
    """One page of records and its opaque continuation cursor."""

    records: tuple[Record, ...]
    next_cursor: str | None


class PageSource(Protocol):
    """Minimal interface implemented by a cursor-paginated API client."""

    def fetch_page(self, cursor: str | None) -> Page:
        """Fetch one page beginning at cursor."""
