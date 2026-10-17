# Supplier verification and metrics corrections

This offline update addresses two measurement findings from the excluded
supplier smoke. It makes no model request, does not repeat an attempt and does
not rewrite the frozen raw runs, historical verifier, scores or prose reviews.

## Evaluation contract 0.3 and verifier 2.1.0

The frozen verifier 2.0.0 compared each conflict's citation set for equality.
A correct additional source therefore caused the same check to fail as a
missing required source. Verifier 2.1.0 requires every mandatory source for each
conflict while allowing additional anchors known in the source blueprint.
Unknown anchors, duplicate sources, duplicate conflict codes and missing
conflicts are rejected. All other eleven checks remain unchanged. Free-text
entailment and source authority still require separate review.

The visible report schema and the supplier dossier stay at 2.0.0. The new
evaluation contract is an additive version and must be selected explicitly for
a new evaluation; existing hash-bound harnesses continue to use their frozen
verifier. No historical result is silently reinterpreted.

```bash
python3 -m local_llm_benchmark.multi_format_transfer_v021 \
  --case tasks/agentic/multi-format-document-analysis/supplier-award-reconciliation/case-v0.2.json \
  --report new-candidate.json
```

The reference-report regression adds a valid Atlas citation: the old verifier
still returns 11/12 while the new verifier accepts all 12 checks. Removing a
required anchor or the reassessment action remains a failure. This regression
uses a synthetic mutation of the project reference, not a new model answer or
rescoring of the completed smoke.

## Metrics contract 0.2.0

The new normalizer preserves unavailable counts as `null`. A complete total is
reported only when every unit records that metric. A subtotal always carries
coverage, so it cannot be confused with the pair total. Explicitly recorded
zero remains distinct from an unavailable count. Contradictory or invalid
counters fail closed.

Pi v0.4 records 18 native tool calls, including one report completion. Its four
artifact counters record 17 inventory/read operations. Mini v0.2 records 17
artifact operations and a separate finish action. The normalized metrics
therefore show 17 artifact operations and one report completion for each.
Pi's six agent turns do not establish its HTTP request count: that metric is
unknown. Mini records 18 requests, so the pair total is unknown with a known
subtotal of 18 covering one of two systems.

```bash
python3 -m local_llm_benchmark.multi_format_metrics_v02 \
  --study-dir results/agentic-transfer-smokes/COMPLETED-STUDY
```

This writes a separately named metrics report and refuses to overwrite existing
destinations. It checks the frozen source plan/controller and agreement between
raw and terminal study trajectories. No runtime client is constructed. The
original study's inherited aggregate and its old report remain historical
artifacts; consumers should use the explicitly versioned metrics report.

The [corrected smoke metrics](../reports/agentic/multi-format-transfer-smoke-v0.3-metrics-v0.2.md)
are derived from the same completed bytes. The
[original deterministic report](../reports/agentic/multi-format-transfer-smoke-v0.3.md)
and [source-grounded review](../reports/agentic/multi-format-transfer-smoke-v0.3-quality-audit.md)
remain unchanged. Counts alone do not establish efficiency or a harness ranking.
