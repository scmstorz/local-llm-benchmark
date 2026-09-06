"""Candidate-hidden acceptance tests for pagination-cycle-guard."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path


if len(sys.argv) != 2:
    raise SystemExit("usage: hidden_tests.py FIXTURE_ROOT")

fixture_root = Path(sys.argv.pop()).resolve()
sys.path.insert(0, str(fixture_root / "src"))

from paged_sync import (  # noqa: E402
    Page,
    PageLimitExceeded,
    PaginationCycleError,
    Record,
    collect_records,
)


class FakeSource:
    def __init__(self, pages: dict[str | None, Page]) -> None:
        self.pages = pages
        self.calls: list[str | None] = []

    def fetch_page(self, cursor: str | None) -> Page:
        self.calls.append(cursor)
        return self.pages[cursor]


class HiddenAcceptanceTest(unittest.TestCase):
    def test_deduplicates_within_and_across_pages_using_first_value(self) -> None:
        source = FakeSource(
            {
                None: Page(
                    (
                        Record("one", "first"),
                        Record("one", "same-page duplicate"),
                    ),
                    "next",
                ),
                "next": Page(
                    (Record("one", "later duplicate"), Record("two", "second")),
                    None,
                ),
            }
        )

        self.assertEqual(
            collect_records(source),
            [Record("one", "first"), Record("two", "second")],
        )

    def test_empty_terminal_page_finishes_normally(self) -> None:
        source = FakeSource({None: Page((), None)})

        self.assertEqual(collect_records(source), [])
        self.assertEqual(source.calls, [None])

    def test_cycle_raises_before_refetching_cursor(self) -> None:
        source = FakeSource(
            {
                None: Page((Record("root", "0"),), "a"),
                "a": Page((Record("one", "1"),), "b"),
                "b": Page((Record("two", "2"),), "a"),
            }
        )

        with self.assertRaises(PaginationCycleError) as caught:
            collect_records(source, max_pages=10)

        self.assertEqual(caught.exception.cursor, "a")
        self.assertEqual(source.calls, [None, "a", "b"])

    def test_cycle_detection_precedes_limit_error(self) -> None:
        source = FakeSource(
            {
                None: Page((Record("root", "0"),), "a"),
                "a": Page((Record("one", "1"),), "a"),
            }
        )

        with self.assertRaises(PaginationCycleError):
            collect_records(source, max_pages=2)

        self.assertEqual(source.calls, [None, "a"])

    def test_page_limit_prevents_one_extra_fetch(self) -> None:
        source = FakeSource(
            {
                None: Page((Record("root", "0"),), "a"),
                "a": Page((Record("one", "1"),), "b"),
                "b": Page((Record("must-not-fetch", "2"),), None),
            }
        )

        with self.assertRaises(PageLimitExceeded) as caught:
            collect_records(source, max_pages=2)

        self.assertEqual(caught.exception.max_pages, 2)
        self.assertEqual(source.calls, [None, "a"])

    def test_invalid_page_limit_has_no_source_side_effect(self) -> None:
        source = FakeSource({None: Page((), None)})

        with self.assertRaises(ValueError):
            collect_records(source, max_pages=0)

        self.assertEqual(source.calls, [])


if __name__ == "__main__":
    unittest.main(verbosity=2)
