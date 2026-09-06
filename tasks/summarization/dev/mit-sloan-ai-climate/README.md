# MIT Sloan AI and climate — development case

Case ID: `summarization.dev.mit-sloan-ai-climate`

This is the first complete benchmark card for the suite. It tests
cross-lingual article summarization from English to German for a reader who
wants to stay informed about current developments.

The case is deliberately classified as `easy_medium`: the source is
information-dense, but it contains a prominent key-findings section and clear
headings. It is suitable for developing the harness and judge workflow, not as
a difficult holdout.

## Versioned files

- `case.json`: executable task contract and file references
- `source-metadata.json`: provenance, hashes and redistribution policy
- `prompt/system.txt`: exact system message
- `prompt/user.md`: exact user-message template
- `benchmark-card.json`: frozen facts, ideas, known errors and scoring rubric
- `judge-instructions.md`: procedure for interactive Codex judging
- `judge-result.schema.json`: machine-validatable judge-result contract

## Private source

The cleaned article is stored at:

```text
data/private/summarization/dev/mit-sloan-ai-climate/source.md
```

The raw HTML and intermediate conversion are kept in the same ignored
directory. None of these files is tracked because the article is copyrighted
and no redistribution license was identified. The source metadata records a
SHA-256 hash of the exact cleaned input so that a run can prove which text it
used.

The cleaned text retains the title, subtitle, byline, publication date, key
findings and article body. Navigation, share controls, a duplicated pull quote,
author biographies and institutional boilerplate are excluded. Stable location
labels such as `[K01]` and `[P04]` are added for judge evidence; the candidate is
explicitly told not to reproduce them.

## Score construction

Coverage is not assigned as a free-form number. The judge marks each frozen
fact and key idea as `full`, `partial`, `missing` or `contradicted`. Weighted
coverage points are derived from those statuses. Five dimensions are scored
with rubric anchors. The maximum is 100 points:

```text
key-fact coverage       25
key-idea coverage       15
factual accuracy        25
epistemic precision     10
prioritization          10
structure and clarity   10
compression              5
```

Critical errors and hard task-constraint violations can cap the final score as
defined in the benchmark card.

