# Coding benchmark track

This track evaluates software-engineering outcomes with deterministic
verification. It does not use an LLM judge as the primary success signal.

The first stage is Track A: the model receives a frozen task description and a
bounded repository snapshot in one prompt, without tools or an agent loop. The
benchmark controller installs the versioned candidate artifact in a disposable
fixture copy and runs public and candidate-hidden tests.

Two artifact contracts and one verifier revision currently remain separate:

- v1 requires a Git-style unified diff and measures directly applicable patch
  production as well as code repair;
- v1.1 requires strict complete-file replacement envelopes and removes diff
  hunk serialization while retaining exact path and content ownership.
- v1.2 keeps the v1.1 visible contract unchanged and adds a missing hidden
  acceptance case for cycles back to a supplied non-empty start cursor.

Track B keeps the task and verifier stable while adding:

1. a pinned Pi coding-agent version; and
2. a project-owned minimal agent harness.

OpenCode remains a later external-harness comparison. Harness families are
reported separately; the suite will not silently pool their outcomes.

The shared protocol, permissions, budgets and current implementation boundary
are documented in [`track-b/`](track-b/README.md). The first measured Pi v0.2
cohort is complete and remains immutable. Pi v0.3 is now qualified without
model inference for PHP, JavaScript and the corrected Python v1.2 case. Its
frozen five-model execution plan subsequently completed all 15 model-task
units, with 9 verified successes.

The first three cases are summarized together in the
[`Coding Track A v0.1 report`](../../reports/coding/coding-track-a-v0.1.md).
Its primary matrix, best-known requirement evidence and transport diagnostics
remain separate; it does not define a universal model ranking.

## Development cases

- [`pagination-cycle-guard`](dev/pagination-cycle-guard/README.md): repair a
  paginated synchronization loop while preserving ordering, deduplication,
  termination and fetch-budget guarantees. The first five-model direct-patch
  comparison completed with zero applicable patches; see the tracked
  [`report`](../../reports/coding/pagination-cycle-guard-track-a-v1.md). The
  v1.1 whole-file runner and verifier produced one excluded successful Ornith
  smoke. Its separate five-model comparison produced four valid artifacts and
  three frozen-verifier passes; a post-hoc task-derived audit found one silent
  false positive. See the v1.1
  [`report`](../../reports/coding/pagination-cycle-guard-track-a-whole-file-v1.1.md).
  Verifier v1.2 catches that false positive in a zero-inference retrospective
  replay; see its separate
  [`report`](../../reports/coding/pagination-cycle-guard-verifier-v1.2-retrospective-replay.md).
- [`async-cache-coalescing`](dev/async-cache-coalescing/README.md): implement
  request coalescing, TTL and invalidation-race semantics in a dependency-free
  JavaScript ES module. The partial baseline fails both test layers; the
  independent reference passes all 4 public and 8 hidden checks. An excluded
  Ornith smoke produced a valid artifact but failed the deterministic verifier
  with 2/4 public and 3/8 hidden checks passing. Its formal five-model plan is
  frozen and executed in counterbalanced `EDACB` order. No deployment achieved
  verified success; Qwen 3.8 came closest with 10/12 checks passing. See the
  [`report`](../../reports/coding/async-cache-coalescing-track-a-v1.md).
- [`php-payment-result-migration`](dev/php-payment-result-migration/README.md):
  complete a typed PHP 8.4 payment-result API migration across a checkout
  service and retry policy. The task separates final stored states, declines,
  ambiguous outcomes and exhausted transient failures while preserving one
  stable idempotency key and exactly one final repository transition. The
  partial baseline passes 2/4 public and 3/8 hidden checks; the independent
  reference passes all twelve. An excluded Ornith smoke emitted two plausible
  PHP code blocks but violated the path-bearing whole-file envelope, so no
  candidate tests ran and the preserved outcome is `malformed_artifact`. A
  separately labeled, code-byte-identical
  transport diagnostic passed all 12 checks without changing that original
  outcome; see its
  [`report`](../../reports/coding/php-payment-result-migration-ornith-smoke-diagnostic.md).
  The subsequent `BCEDA` comparison ended with 0/5 strict successes. Its frozen
  secondary diagnostic confirmed Ornith at 12/12; post-hoc byte-preserving
  audits also confirmed Qwen 3.8 and Glimmer, while Qwen 3.6 had invalid PHP and
  GPT-OSS returned no code. See the layered
  [`comparison report`](../../reports/coding/php-payment-result-migration-track-a-v1.md).
