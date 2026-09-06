"""Stable public exceptions for pagination failures."""


class PaginationError(RuntimeError):
    """Base class for bounded pagination failures."""


class PaginationCycleError(PaginationError):
    """Raised before a cursor would be fetched for a second time."""

    def __init__(self, cursor: str) -> None:
        self.cursor = cursor
        super().__init__(f"pagination cursor repeated: {cursor}")


class PageLimitExceeded(PaginationError):
    """Raised when another page exists beyond the declared fetch budget."""

    def __init__(self, max_pages: int) -> None:
        self.max_pages = max_pages
        super().__init__(f"pagination exceeded the {max_pages}-page limit")
