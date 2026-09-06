# Async cache coalescing

Case ID: `coding.dev.async-cache-coalescing`

This is the second Track A development case and the first JavaScript case. It
asks a model to complete a dependency-free asynchronous TTL cache whose
ordinary sequential caching already works but whose overlap and invalidation
semantics are incomplete.

## Why this case

The first coding case was a Python pagination bug centered on synchronous
control flow and boundary ordering. This case changes both the language and
the failure surface:

- JavaScript ES modules on Node.js 22;
- asynchronous concurrency rather than a sequential loop;
- coalescing and per-key independence;
- rejection cleanup;
- stale completion after targeted or global invalidation;
- TTL measured from fulfillment.

The task is categorized as `feature_implementation`, not `bug_fixing`. Its
task profile remains descriptive; difficulty will be inferred from observed
model outcomes rather than assigned in advance.

## Track A contract

The candidate receives the task, package metadata, two source modules and four
public tests in one prompt. It receives no tools, hidden tests or test feedback.
Its response may replace one or two existing `src/*.mjs` files using the
strict whole-file envelope. Tests and `package.json` are protected.

The verifier runs with no installed package dependencies. It records
`node --version`, executes the four public `node:test` cases and then runs eight
candidate-hidden checks from outside the disposable fixture.

## Current validation state

The frozen baseline is intentionally partial: three of four public tests and
five of eight hidden checks pass. It fails same-key request coalescing, shared
rejection behavior and both in-flight invalidation races. The independent
reference implementation passes all twelve checks. This red-baseline and
green-reference validation was complete before any model output was executed.

The excluded Ornith development smoke is now complete. It returned one valid,
scope-safe replacement module and reached both deterministic layers, but
passed only 2/4 public tests and 3/8 hidden checks. The observed outcome is
`verified_success=false` with `failure_code=public_tests_failed`. Its central
condition cached a successful result only when the key was absent from the
in-flight map, reversing normal cache population and stale-invalidation
ownership. This smoke is not part of a formal comparison or reliability
estimate.

## Executed comparison

[`comparison-plan.json`](comparison-plan.json) preregisters a five-model Track
A Capability Sweep in `EDACB` order: Ornith, Muse Glimmer, Qwen 3.6, GPT-OSS
and Qwen 3.8. Each deployment receives one cold attempt with the same frozen
prompt, fixture, whole-file artifact contract and inference settings. There is
no warm-up, retry, repair, test feedback or adaptive repeat.

The order gives every model a position it did not occupy in any of the three
distinct earlier five-model order designs. The excluded Ornith smoke is not
reused; Ornith received a fresh post-freeze attempt like every other model.

The comparison is complete with 0/5 verified successes. Qwen 3.8 came closest
with 4/4 public and 6/8 hidden checks, followed by Muse Glimmer with 4/4 and
5/8. Ornith and Qwen 3.6 each passed 2/4 and 3/8. GPT-OSS exhausted its output
budget without exposing a candidate file. See the tracked
[`JSON`](../../../../reports/coding/async-cache-coalescing-track-a-v1.json) and
[`Markdown`](../../../../reports/coding/async-cache-coalescing-track-a-v1.md)
reports. Partial counts remain diagnostic and do not replace verified success.
