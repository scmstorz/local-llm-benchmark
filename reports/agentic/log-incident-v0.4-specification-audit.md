# Agentic Log Incident v0.4 Specification Audit

The six-cell v0.4 confirmation completed technically and verified that the
three v0.3 alignment repairs work as implemented. Its official result remains
**1/6 semantic successes**. Post-run human calibration nevertheless found two
new verifier false negatives and one blocking representation ambiguity, so the
result must not yet be expanded into a broad model sweep.

## Official outcomes

| Position | System | Case | Runtime | Strict JSON | Official result | Checks | Active time |
| ---: | --- | --- | --- | --- | --- | ---: | ---: |
| 1 | Mini | Checkout pool regression | complete | yes | task failure | 14/15 | 87.29 s |
| 2 | Pi 0.84.4 | Retry queue amplification | complete | no; normalized | task failure | 14/15 | 138.15 s |
| 3 | Mini | Clock skew partial recovery | complete | yes | success | 15/15 | 78.06 s |
| 4 | Pi 0.84.4 | Checkout pool regression | complete | no; normalized | task failure | 14/15 | 297.70 s |
| 5 | Mini | Retry queue amplification | complete | yes | task failure | 13/15 | 82.15 s |
| 6 | Pi 0.84.4 | Clock skew partial recovery | complete | yes | task failure | 13/15 | 128.80 s |

All six runs completed technically with valid agent termination and preserved
reports. Four final responses were bare JSON. The frozen normalizer recovered
one intact object from each of the other two responses without repairing their
contents. Pi completed the clock-skew cell that had timed out in v0.3.

## What v0.4 successfully repaired

The known v0.3 defects did not recur in their original forms:

- ordinary separator and conjunction variants of the expected scope labels no
  longer failed;
- alternative predeclared counter-evidence groups were accepted instead of one
  exhaustive reference-author set;
- the clock-skew report passed critical evidence with direct single-role
  assignments and without duplicate citations.

All six schema-valid reports also passed the three independent temporal checks,
the schema boundary, citation integrity, root cause, trigger, critical evidence,
bounded impact, remediation and uncertainty checks. The v0.3 repair therefore
remains valid.

## Blocking alignment findings

Manual comparison of every failed check with the visible task and candidate
report found three issues that prevent clean capability attribution:

1. Positions 1 and 4 rejected the authentication alternative with healthy
   customer-token evidence and explicitly named the unrelated admin-token event
   in the same structured entry's reason. The verifier reads only
   `evidence_ids`, where the reports listed the healthy-token event alone. The
   visible wording says to attach direct evidence within the entry but does not
   state whether an exact event ID in `reason` is ignored. This is a blocking
   representation ambiguity. A later contract must say explicitly that only
   `evidence_ids` count, or the verifier must validate citations across the
   complete entry.
2. Position 5 correctly said that no orders were lost, checkout remained
   available and production notifications were unaffected. The verifier uses
   raw forbidden-fragment substring matching, so the negated phrase was treated
   as the prohibited positive claim. This is a benchmark false negative.
3. Position 6 identified the correct `payment-validation` service and added the
   correct failing node in parentheses. Token-set equality rejected this
   compatible specialization because of the additional host tokens. This is a
   benchmark false negative, while unrestricted subset matching would be too
   permissive for other scopes.

These findings do not change the frozen official result.

## Candidate-attributable failures

Three reports also contain genuine causal-chain failures:

- Position 2 omits the immediate zero-delay retry event and the intermediate
  queue-draining waypoint.
- Position 5 omits the immediate zero-delay retry event.
- Position 6 places the user-facing edge error before the causally prior
  skewed-node rejection and omits the later intermittent-rejection event.

Positions 2 and 4 also correctly fail strict transport compliance because Pi
wrapped one intact report object in surrounding text. Normalization preserved
their semantic evaluation as designed.

## Decision

Do not run a broad v0.4 model sweep. Preserve v0.4 as excluded protocol evidence
and create an additive v0.5 contract that:

- makes structured evidence attachment semantics explicit;
- removes negation-blind substring scoring from free-text summaries;
- uses visible canonical scope identifiers or separates canonical service from
  optional component detail;
- retains the validated time semantics, evidence-role repair, response
  normalizer, read-only isolation and user-facing timeout;
- requalifies focused positive and negative controls before another small gate.

A diagnostic aligned interpretation would leave positions 1, 3 and 4 with no
semantic miss, while positions 2, 5 and 6 would retain genuine causal-chain
failures. This is diagnostic only and is not a rescore.

## Interpretation limits

Each cell has `n=1`; this confirmation estimates neither model reliability nor
quality stochasticity. Its timing is descriptive only. Mini and Pi remain
complete-system conditions, not an isolated one-factor harness comparison.

