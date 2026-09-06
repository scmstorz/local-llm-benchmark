# Fix cursor pagination termination and deduplication

`paged_sync.collect_records()` collects records from an API that uses opaque
continuation cursors. The current implementation works for simple pages but is
unsafe for production-shaped pagination.

Change the implementation so that all of these requirements hold:

1. Fetch the first page with the supplied `start_cursor`, including `None`.
2. Return records in first-seen order and include each `Record.identifier` at
   most once, including duplicates within one page and overlaps between pages.
3. An empty page is not terminal when it supplies a non-`None` next cursor.
4. Never fetch the same non-terminal cursor twice. If a next cursor has already
   been fetched, raise `PaginationCycleError` with that repeated cursor.
5. `max_pages` is the maximum number of calls to `fetch_page`. When another
   distinct cursor remains after that budget is exhausted, raise
   `PageLimitExceeded` without performing an extra fetch.
6. Cycle detection takes precedence when the repeated cursor and the page limit
   are discovered at the same boundary.
7. Reject `max_pages < 1` with `ValueError` before calling the source.

Preserve the existing public API and exception classes. Add no dependencies.
Only files under `src/paged_sync/` may be changed; do not modify tests or
project metadata.
