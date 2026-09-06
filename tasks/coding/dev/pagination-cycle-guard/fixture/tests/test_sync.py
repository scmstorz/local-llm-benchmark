"""Candidate-visible regression tests for paged_sync."""

from __future__ import annotations

import unittest

from paged_sync import Page, Record, collect_records


class FakeSource:
    def __init__(self, pages: dict[str | None, Page]) -> None:
        self.pages = pages
        self.calls: list[str | None] = []

    def fetch_page(self, cursor: str | None) -> Page:
        self.calls.append(cursor)
        return self.pages[cursor]


class CollectRecordsTest(unittest.TestCase):
    def test_collects_multiple_pages_in_order(self) -> None:
        source = FakeSource(
            {
                None: Page((Record("one", "A"),), "next"),
                "next": Page((Record("two", "B"),), None),
            }
        )

        records = collect_records(source)

        self.assertEqual([record.identifier for record in records], ["one", "two"])
        self.assertEqual(source.calls, [None, "next"])

    def test_continues_after_empty_nonterminal_page(self) -> None:
        source = FakeSource(
            {
                None: Page((), "next"),
                "next": Page((Record("one", "A"),), None),
            }
        )

        records = collect_records(source)

        self.assertEqual(records, [Record("one", "A")])
        self.assertEqual(source.calls, [None, "next"])

    def test_deduplicates_overlapping_pages_by_identifier(self) -> None:
        source = FakeSource(
            {
                None: Page(
                    (Record("one", "first"), Record("two", "original")),
                    "next",
                ),
                "next": Page(
                    (Record("two", "duplicate"), Record("three", "last")),
                    None,
                ),
            }
        )

        records = collect_records(source)

        self.assertEqual(
            records,
            [
                Record("one", "first"),
                Record("two", "original"),
                Record("three", "last"),
            ],
        )

    def test_uses_supplied_start_cursor(self) -> None:
        source = FakeSource(
            {"resume": Page((Record("one", "A"),), None)}
        )

        collect_records(source, start_cursor="resume")

        self.assertEqual(source.calls, ["resume"])


if __name__ == "__main__":
    unittest.main()
