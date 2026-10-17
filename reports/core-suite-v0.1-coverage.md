# Core-suite v0.1 coverage inventory

The provisional inventory has **23 tasks and 35 applicable task/system variants**.
Model membership is open. This inventory links existing historical evidence; it
does not count old runs as a matched current-runtime comparison.

Supplier evidence is excluded development smoke under the old evaluator.
The corrected future supplier configuration has no measured coverage yet.
Python direct coding uses case/verifier 1.2; its older direct measurement used 1.1.

| Task | Version | Applicable systems | Historical evidence |
| --- | --- | --- | --- |
| summarization.dev.mit-sloan-ai-climate | 1.1.0 | direct-text | [historical measurement](challenger-sweeps/september-2026-model-cohort-quality.json) |
| summarization.dev.the-agent-company | 1.0.0 | direct-text | [historical measurement](challenger-sweeps/september-2026-model-cohort-quality.json) |
| summarization.dev.metr-long-software-tasks | 1.0.0 | direct-text | [historical measurement](challenger-sweeps/september-2026-model-cohort-quality.json) |
| general_knowledge.dev.confidence-intervals | 1.0.0 | direct-text | [historical measurement](challenger-sweeps/september-2026-model-cohort-quality.json) |
| general_knowledge.dev.confidence-intervals-transfer | 1.0.0 | direct-text | [historical measurement](challenger-sweeps/september-2026-model-cohort-quality.json) |
| general_knowledge.dev.mrna-vaccine-mechanism | 1.0.0 | direct-text | [historical measurement](challenger-sweeps/september-2026-model-cohort-quality.json) |
| general_knowledge.dev.interest-rates-and-inflation | 1.0.0 | direct-text | [historical measurement](challenger-sweeps/september-2026-model-cohort-quality.json) |
| general_knowledge.dev.medical-screening-bayes | 1.0.0 | direct-text | [historical measurement](challenger-sweeps/september-2026-model-cohort-quality.json) |
| general_knowledge.dev.antibiotic-resistance | 1.0.0 | direct-text | [historical measurement](challenger-sweeps/september-2026-model-cohort-quality.json) |
| general_knowledge.dev.renewable-electricity-matching | 1.0.0 | direct-text | [historical measurement](challenger-sweeps/september-2026-model-cohort-quality.json) |
| general_knowledge.dev.distributed-payment-reliability | 1.0.0 | direct-text | [historical measurement](challenger-sweeps/september-2026-model-cohort-quality.json) |
| general_knowledge.dev.ml-evaluation-leakage | 1.0.0 | direct-text | [historical measurement](challenger-sweeps/september-2026-model-cohort-quality.json) |
| general_knowledge.dev.rag-grounding-evaluation | 1.0.0 | direct-text | [historical measurement](challenger-sweeps/september-2026-model-cohort-quality.json) |
| source_grounded_writing.dev.ai-transformation-value-gap | 1.0.0 | direct-text | [historical measurement](challenger-sweeps/september-2026-model-cohort-quality.json) |
| source_grounded_writing.dev.agentic-software-development-reality-gap | 1.0.0 | direct-text | [historical measurement](challenger-sweeps/september-2026-model-cohort-quality.json) |
| coding.dev.pagination-cycle-guard | 1.2.0 | direct-coding, mini-coding, pi-coding | [historical measurement (older evaluation)](coding/coding-track-a-v0.1.json); [historical measurement](coding/track-b-pi-vs-mini-system-comparison-v0.3.json) |
| coding.dev.async-cache-coalescing | 1.0.0 | direct-coding, mini-coding, pi-coding | [historical measurement](coding/coding-track-a-v0.1.json); [historical measurement](coding/track-b-pi-vs-mini-system-comparison-v0.3.json) |
| coding.dev.php-payment-result-migration | 1.0.0 | direct-coding, mini-coding, pi-coding | [historical measurement](coding/coding-track-a-v0.1.json); [historical measurement](coding/track-b-pi-vs-mini-system-comparison-v0.3.json) |
| agentic.ops.checkout-pool-regression | 5.0.0 | mini-log, pi-log | [historical measurement](agentic/log-incident-capability-sweep-v0.5.json) |
| agentic.ops.retry-queue-amplification | 5.0.0 | mini-log, pi-log | [historical measurement](agentic/log-incident-capability-sweep-v0.5.json) |
| agentic.ops.clock-skew-partial-recovery | 5.0.0 | mini-log, pi-log | [historical measurement](agentic/log-incident-capability-sweep-v0.5.json) |
| agentic.documents.rollout-readiness-reconciliation | 1.0.0 | canonical-rollout, mini-rollout, pi-rollout | [historical measurement](agentic/multi-format-capability-sweep-v0.1.json) |
| agentic.documents.supplier-award-reconciliation | 2.0.0 | mini-supplier, pi-supplier | [excluded smoke, old evaluation](agentic/multi-format-transfer-smoke-v0.3.json) |

Supplier direct/canonical execution has no admitted runner. Additional harnesses
need their own versioned registry mapping and qualification.

Use the [shared workflow](../docs/core-suite-v0.1.md) for a fresh bound plan and
its result coverage. See the [machine-readable inventory](core-suite-v0.1-coverage.json)
for source paths, evidence classes, evaluator differences and deferred work.
