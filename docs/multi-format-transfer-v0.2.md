# Multi-Format Transfer Case v0.2

## Objective

Phase 96 tests whether the read-only multi-format result transfers to a second
decision shape rather than accumulating more repetitions on the original
rollout case. The new synthetic case is
`agentic.documents.supplier-award-reconciliation`.

The case asks a sourcing committee to select one primary supplier and one
reserve. It deliberately changes both domain and reasoning structure. The
original case independently applied gates to regions; this case first filters
suppliers using policy, signed-final assurance and formula-derived commercial
facts, then ranks only the eligible suppliers by adjusted first-year cost.

## Controlled outcome

Four suppliers appear in the frozen dossier:

- Atlas is eligible at EUR 1,140,000 adjusted first-year cost and 16% capacity
  headroom;
- Boreal is eligible at EUR 1,165,000 and 25% headroom;
- Cedar is commercially cheapest at EUR 1,080,000 but has one unresolved
  critical finding in the signed-final assurance;
- Delta costs EUR 1,130,000 and passes assurance, but its 12% capacity headroom
  is below the 15% minimum.

The correct decision is `award_with_reserve`: Atlas is primary, Boreal is
reserve, Cedar is rejected for `unresolved_critical_finding`, and Delta is
rejected for `capacity_headroom_below_threshold`.

## Necessary cross-format evidence

The Word policy defines four eligibility gates, the filter-then-rank sequence,
evidence authority and the decision cutoff. The PDF contains an unsigned draft
followed by an explicitly superseding signed-final assurance appendix. The
workbook calculates adjusted first-year cost and capacity
headroom, while an intentionally incomplete commercial dashboard recommends
Cedar without incorporating assurance.

No format is ornamental. The policy defines what to calculate and how to rank;
the PDF determines assurance eligibility; the workbook determines commercial
eligibility and the order among survivors.

## Transfer controls

The case reuses no source binary, candidate response, entity name, numeric
value, cutoff or source anchor from v0.1. It replaces independent regional
approval with constrained selection, creates two eligible candidates that must
be ordered, makes the cheapest candidate ineligible for a non-commercial
reason, and gives another rejected candidate a formula-derived capacity failure.

The report schema is correspondingly versioned. Its 12 deterministic checks
separate award mode, primary, reserve and supplier blockers while retaining
exact citation, required-evidence, cross-format, conflict, action, uncertainty
and controlled-value checks. The reference report passes 12/12. Free-text
grounding, polarity, German quality and decision usefulness remain a separate
review.

## Current gate

The case is qualified offline through the artifact-API layer and both complete
Track B systems without Ollama contact. Explicit Phase 96 amendments authorize
the controlled alternative
authoring runtimes: python-docx for Word, ReportLab for PDF and openpyxl plus a
LibreOffice recalculation pass for Excel. The Word and spreadsheet render paths
use LibreOffice and Poppler; the PDF uses Poppler directly. Every rendered page
and sheet was inspected, all structural and accessibility checks passed, and
the final binary hashes are frozen.

The canonical representation contains 16 evidence records and rebuilds exactly
from the three frozen binaries. The independent bounded Track B backend exposes
the same records through 16 allowlisted queries, verifies every binary identity
before reading and rejects symlinks, changed bytes, extra workspace files and
unknown anchors. It neither loads ground truth nor contains controlled answers.

Mini v0.2 adapts the already qualified minimal JSON-action kernel through a
versioned case wrapper. It freezes the new task and report schema, exact
supplier fixture root, prompt, action schema, inventory, isolation profile and
shared backend identity. Its mocked model boundary records one request without
network access, and the reference report completes with strict 12/12 semantic
acceptance.

Pi v0.4 is a separate additive system identity; the Phase 95 v0.3 implementation
and observations remain immutable. Its extension registers the four bounded
artifact readers plus one schema-constrained `finish_report` operation.
Successful completion captures exactly one validated report with exclusive
file creation and shuts the agent down. Surrounding assistant prose is never an
output candidate, duplicate completion fails closed and no post-hoc free-text
normalization is permitted. A real no-inference preparation passed 13/13
Seatbelt checks, including extension load, all three formats and structured
report capture. The acceptance probe used an isolated IPv6 loopback listener
because Ollama occupied only the IPv4 benchmark port; Ollama received no
request.

The complete research regression passes 596 tests, the dependency-free public
registry passes 414 tests and the Pi suite passes 34 tests with one expected
opt-in transport skip.

The separate smoke plan is now frozen with SHA-256
`c2dd3235a8378a9f9dcced40dbb53e5d1f3a46f3a693d3dff24d5067b96d6302`.
It schedules exactly one Qwen 3.8 attempt under Pi v0.4 followed by one under
Mini v0.2. The repair-first order is fixed before inference, every terminal
outcome is preserved, no retry or adaptive repetition is allowed and the pair
cannot enter measured aggregates or support ranking claims. The
no-inference-qualified controller can prepare both runs offline and produces a
public-safe deterministic report after completion. An offline Pi acceptance is
only readiness evidence; a fresh 13-check acceptance remains mandatory after
the resource gate immediately before Pi inference.

The repository intentionally contains no execution authorization artifact.
Any Ollama request requires a new authorization bound to the exact frozen plan
hash plus a fresh exclusive-window confirmation and resource gate.

After freeze commit `456dcfd`, the controller prepared both private units with
zero model requests. Pi is `sandbox_ready` after an offline 13/13 readiness
acceptance and Mini is `awaiting_model`. The missing authorization was also
tested at the actual study boundary: `live` stopped before constructing an
Ollama client. No further useful offline execution step remains.

Machine-readable entry points are the
[case](../tasks/agentic/multi-format-document-analysis/supplier-award-reconciliation/case-v0.2.json),
[task](../tasks/agentic/multi-format-document-analysis/supplier-award-reconciliation/TASK-v0.2.md),
[source blueprint](../tasks/agentic/multi-format-document-analysis/supplier-award-reconciliation/source-blueprint-v0.2.json),
[ground truth](../tasks/agentic/multi-format-document-analysis/supplier-award-reconciliation/reference/ground-truth-v0.2.json),
[reference report](../tasks/agentic/multi-format-document-analysis/supplier-award-reconciliation/reference/reference-report-v0.2.json),
[report schema](../tasks/agentic/multi-format-document-analysis/report-schema-v2.json),
[evaluation contract](../tasks/agentic/multi-format-document-analysis/evaluation-contract-v0.2.json),
[canonical schema](../tasks/agentic/multi-format-document-analysis/canonical-extraction-schema-v2.json)
and [offline qualification](../tasks/agentic/multi-format-document-analysis/supplier-award-reconciliation/offline-qualification-v0.2.json). The frozen
[canonical extraction](../tasks/agentic/multi-format-document-analysis/supplier-award-reconciliation/canonical/canonical-extraction-v0.2.json)
and its [qualification](../tasks/agentic/multi-format-document-analysis/supplier-award-reconciliation/canonical-extraction-qualification-v0.2.json)
provide Track A; the [artifact API qualification](../tasks/agentic/track-b/multi-format-transfer-artifact-api-v0.2-qualification.json)
binds the Track B parser boundary. The complete-system records are the
[Mini v0.2 qualification](../tasks/agentic/track-b/mini-multi-format-v0.2-qualification.json),
[Pi v0.4 qualification](../tasks/agentic/track-b/pi-multi-format-v0.4-qualification.json)
and their [combined qualification](../tasks/agentic/track-b/multi-format-transfer-complete-systems-v0.2-qualification.json).
The next-layer [excluded smoke plan](../tasks/agentic/track-b/multi-format-transfer-smoke-v0.2.json)
and [controller qualification](../tasks/agentic/track-b/multi-format-transfer-smoke-v0.2-controller-qualification.json)
freeze the live boundary without granting it.
