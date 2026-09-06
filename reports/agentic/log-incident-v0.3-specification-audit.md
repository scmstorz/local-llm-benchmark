# Agentic Log Incident v0.3 Specification Audit

The six-cell confirmation did its job: it showed that v0.3 fixed the original
timestamp ambiguity, but it also found three remaining task-to-verifier
alignment defects. The official result remains **0/6 semantic successes**. It
must not be used for a broader model comparison.

## Official outcomes

| Position | System | Case | Runtime | Strict JSON | Official result | Checks |
| ---: | --- | --- | --- | --- | --- | ---: |
| 1 | Mini | Checkout pool regression | complete | yes | task failure | 14/15 |
| 2 | Pi 0.84.4 | Retry queue amplification | complete | no; normalized | task failure | 12/15 |
| 3 | Mini | Clock skew partial recovery | complete | yes | task failure | 12/15 |
| 4 | Pi 0.84.4 | Checkout pool regression | complete | yes | schema failure | 0/1 |
| 5 | Mini | Retry queue amplification | complete | yes | task failure | 12/15 |
| 6 | Pi 0.84.4 | Clock skew partial recovery | 300 s timeout | no final object | runtime failure | 0/1 |

Five runs completed technically and five candidate reports were preserved.
Four reports passed the strict schema gate. Four of six final responses were
bare JSON; the predeclared normalizer recovered one additional intact object
from surrounding text. The last Pi run timed out while generating its final
response.

## What v0.3 successfully repaired

The temporal semantics are now clear. Every schema-valid report passed all
three independent time/recovery checks:

- `incident_start_utc`: 4/4;
- `last_observed_utc`: 4/4;
- `recovery_status`: 4/4.

The fifth produced report stopped at the schema gate, but a diagnostic review
found the same three correct values. This is strong specification-confirmation
evidence that the explicit definition of user-impact onset fixed the dominant
v0.2 problem. It is not a reliability estimate.

The response normalizer also behaved exactly as frozen. It recovered one and
only one intact JSON object without repairing its contents, while strict
transport compliance remained a separate result.

## Remaining alignment defects

Manual calibration found seven failed-check instances that cannot cleanly be
attributed to model capability:

1. `affected_scope` failed three times because correct human-readable journeys
   did not byte-match hidden underscore-delimited identifiers. The visible task
   does not define these fields as controlled codes.
2. `distractor_rejection` failed three times even though each report rejected
   the required alternatives and attached direct counter-evidence. The verifier
   requires the reference author's complete event-ID set rather than sufficient
   evidence under the visible rule. The schema-invalid fourth report has the
   same issue in a schema-only diagnostic.
3. `critical_evidence` failed once because hidden truth requires one event under
   both `root_cause` and `symptom`, and requires a user-facing intermittent-
   rejection signal as `symptom` even though the visible guidance permits
   `impact`. The task neither requires duplicate entries nor privileges one
   hidden reference-author role where its own role guidance permits another.

These are verifier false negatives, not permission to improve candidate answers
after seeing the result. The official records and the 0/6 primary outcome remain
unchanged.

## Candidate-attributable failures

The audit also found genuine system errors:

- Both retry-queue reports omitted an immediate-retry waypoint from the causal
  chain. The clock-skew report did not reconstruct the rejection/error pair in
  corrected causal order.
- One Pi report used `rationale` rather than the required `reason` field for
  uncertainty items.
- The final Pi cell reached the frozen 300-second user-facing timeout during
  its fourth turn, before a complete final report or valid agent termination.
- One completed Pi response needed the allowed outer-envelope normalization and
  therefore correctly failed strict transport compliance.

## Decision

Do not run the broad v0.3 model sweep. Preserve v0.3 as excluded protocol
evidence and build an additive v0.4 representation that:

- exposes canonical scope values or accepts semantically equivalent strings;
- checks accepted groups of sufficient counter-evidence instead of one hidden
  exhaustive event set;
- removes hidden duplicate-role and single-reference-role requirements or
  explicitly defines them;
- retains the validated temporal rules, schema boundary, response normalizer
  and 300-second timeout.

After offline references and targeted near misses pass, freeze another small
confirmation. Only then decide whether a multi-model capability sweep is worth
the runtime.

## Interpretation limits

Each cell has `n=1`. This confirmation estimates neither reliability nor
quality stochasticity, and its descriptive timing was observed under documented
Spotlight and Docker background load. Mini and Pi are complete systems with
different prompts, tools and context handling; the result is not an isolated
causal estimate of harness quality.
