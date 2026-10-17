# Core runtime readiness v0.1

Exactly one fresh Qwen 3.8 supplier attempt per system ran under Ollama 0.40.5.
Both are excluded development observations. A background model download was
declared; elapsed times support no performance comparison. There were no
model retries, and no historical answer or score was changed.

The shared core plan, fresh-run supplier lifecycle, verifier 2.1.0 and metrics
0.2.0 were exercised together. The sole Pi attempt had a fresh 13-check
sandbox acceptance. See the [workflow](../../docs/core-suite-v0.1.md).

| System | Runtime | Strict transport | Checks | Grounded prose | Artifact operations | Completion | Requests |
| --- | --- | --- | --- | --- | --- | --- | --- |
| mini | True | True | 11/12 | False | 17 | 1 | 18 |
| pi | True | True | 11/12 | True | 17 | 1 | unknown |

Pi's missing HTTP request count remains unknown; agent rounds do not replace it.
The aggregate request total is unknown whenever either system lacks that metric.

## Source-grounded review

The interactive review was not blinded and used no separate paid judge API.

- **mini**: deterministic misses: action_plan. The correct supplier decision and blockers are grounded, but the executive summary and draft-conflict resolution call the explicitly unsigned draft signed, contradicting the evidence entry. The required reassessment action is missing.

- **pi**: deterministic misses: conflict_resolution. The decision, numerical gates and unsigned-draft/signed-final distinction are grounded. The dashboard conflict omits its mandatory policy anchor from its own source_refs, despite citing that policy elsewhere; deterministic success remains false.

## Preparation findings

The resource gate caught a surviving Mnemosyn backend before any inference.
A prepared-Pi record-shape assumption was repaired only in the private
orchestrator before Pi made any request; Mini was not repeated. The original
driver, exact amendment and prepared-run hash remain in private evidence.

Registration also exposed an API-contract mismatch: `/api/tags` identifies
the artifact, while `/api/show` advertises capabilities. The corrected
metadata-only registration has two new regressions; the full research suite
passes 667 tests. Existing catalog records remain unchanged.

These checks do not fill the future measured comparison. Candidate selection,
download completion and fresh matched-runtime reference runs remain separate.

## Coverage identity

Pi keeps observed deployment identity in the controller resource gate rather
than the native run record. The additive [coverage reader 0.2](../../docs/core-records-v0.2.md)
validates exact plan/run hashes and pre-inference observations. It preserves
unknown identity without evidence and cannot override a native contradiction.
Both completed attempts are observed coverage; neither passed every semantic
check, and neither is promoted into measured comparison coverage.
