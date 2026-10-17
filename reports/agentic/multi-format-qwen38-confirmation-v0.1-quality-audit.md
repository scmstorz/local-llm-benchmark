# Multi-Format Qwen 3.8 Confirmation v0.1 — Quality Audit

The separate interactive Codex review covers all nine parseable candidate
reports. It evaluates source grounding, claim polarity, wording accuracy,
calibration, German presentation and steering usefulness. It neither repairs
nor overrides runtime, schema, deterministic semantic or strict-transport
outcomes.

## Result

| Outcome | Count |
| --- | ---: |
| Parseable reports | 9/9 |
| Free-text pass | 6/9 |
| Free-text fail | 3/9 |
| Deterministic semantic success | 5/9 |
| Deterministic and free-text accepted | 5/9 |
| Deterministic, free-text and strict transport accepted | 3/9 |

The passing prose positions are 2, 3, 4, 5, 7 and 9. Positions 1, 6 and 8
fail because all three canonical-condition reports approve West even though
they cite its 94% completion against the policy's 95% minimum. The three
canonical reports are byte-identical, including this contradiction.

All five deterministic successes also pass the prose review. Position 7 has a
grounded and decision-useful North-only report, but its `schema_version` is
`1.0` instead of `1.0.0`; it therefore remains a deterministic 0/11 failure.
The prose audit does not repair that schema result. Position 9 contains several
ASCII transliterations and one malformed rendering of *maßgeblich*, but its
German meaning and every material conclusion remain unambiguous and safe.

## Condition interpretation

- Canonical Track A: 0/3 deterministic success and 0/3 prose acceptance; all
  three attempts reproduce the same West-approval error.
- Mini v0.1: 3/3 deterministic success, 3/3 prose acceptance and 3/3 strict
  transport.
- Pi v0.3: 2/3 deterministic success and 3/3 prose acceptance; all three
  reports required surrounding-text normalization, and the third has the
  schema-version defect.

These results describe bounded consistency under one fixed Qwen 3.8
deployment, prompt, seed and temperature. Three attempts per condition do not
estimate population reliability, latency tails or a one-factor harness effect.
The judge was not blinded and monitored the study, so this audit is not an
independent-assessor result.
