"""Deterministic output checks for the first summarization slice."""

from __future__ import annotations

import re
from typing import Any


WORD_RE = re.compile(r"[^\W_]+(?:[-’'][^\W_]+)*", re.UNICODE)
SOURCE_LABEL_RE = re.compile(r"\[(?:H|K|P|S|T)\d{2}\]")
MARKDOWN_HEADING_RE = re.compile(r"^\s{0,3}#{1,6}\s+\S", re.MULTILINE)
BOLD_HEADING_RE = re.compile(r"^\s*\*\*[^*\n]{3,}\*\*\s*$", re.MULTILINE)
REASONING_MARKUP_RE = re.compile(r"</?think>", re.IGNORECASE)

GERMAN_STOPWORDS = {
    "aber",
    "als",
    "auch",
    "auf",
    "aus",
    "bei",
    "das",
    "dass",
    "dem",
    "den",
    "der",
    "des",
    "die",
    "durch",
    "ein",
    "eine",
    "einer",
    "einem",
    "einen",
    "für",
    "hat",
    "im",
    "in",
    "ist",
    "mit",
    "nicht",
    "oder",
    "sich",
    "sind",
    "und",
    "von",
    "war",
    "werden",
    "wie",
    "zu",
    "zum",
    "zur",
}

ENGLISH_STOPWORDS = {
    "a",
    "an",
    "and",
    "are",
    "as",
    "at",
    "be",
    "but",
    "by",
    "for",
    "from",
    "has",
    "in",
    "is",
    "it",
    "not",
    "of",
    "on",
    "or",
    "that",
    "the",
    "their",
    "this",
    "to",
    "was",
    "were",
    "which",
    "will",
    "with",
}


def words(text: str) -> list[str]:
    return WORD_RE.findall(text)


def detect_language_heuristic(text: str) -> tuple[str | None, int, int]:
    tokens = [token.casefold() for token in words(text)]
    german_hits = sum(token in GERMAN_STOPWORDS for token in tokens)
    english_hits = sum(token in ENGLISH_STOPWORDS for token in tokens)
    minimum_hits = 3
    if german_hits >= minimum_hits and german_hits > english_hits * 1.25:
        return "de", german_hits, english_hits
    if english_hits >= minimum_hits and english_hits > german_hits * 1.25:
        return "en", german_hits, english_hits
    return None, german_hits, english_hits


def evaluate_output(text: str, maximum_words: int) -> dict[str, Any]:
    token_count = len(words(text))
    detected_language, german_hits, english_hits = detect_language_heuristic(text)
    markdown_heading_count = len(MARKDOWN_HEADING_RE.findall(text))
    bold_heading_count = len(BOLD_HEADING_RE.findall(text))
    structural_heading_count = markdown_heading_count + bold_heading_count
    return {
        "check_version": "1.0.0",
        "nonempty": bool(text.strip()),
        "detected_language": detected_language,
        "language_method": "stopword_heuristic_v1",
        "language_evidence": {
            "german_stopword_hits": german_hits,
            "english_stopword_hits": english_hits,
        },
        "language_pass": detected_language == "de",
        "word_count": token_count,
        "maximum_words": maximum_words,
        "maximum_words_pass": token_count <= maximum_words,
        "source_location_labels_absent": SOURCE_LABEL_RE.search(text) is None,
        "markdown_heading_count": markdown_heading_count,
        "bold_heading_count": bold_heading_count,
        "structural_heading_count": structural_heading_count,
        "heading_pass": structural_heading_count >= 1,
        "reasoning_markup_absent": REASONING_MARKUP_RE.search(text) is None,
    }
