# Agentic software development reality gap — execution report

## Evidence status

This report records execution integrity only. It deliberately omits the private
candidate-to-model mapping, model-specific performance and candidate prose.
Quality judgment has not started. This document preserves the state and claims
available before judgment and unblinding.

## Comparison

- comparison ID: `comparison-20260901T073315Z-42a44ad5`
- case: `source_grounded_writing.dev.agentic-software-development-reality-gap`
- harness commit: `e6ee3dc458ab4aebe0338b8d42c1ecdcb411c88d`
- Ollama version: `0.32.15`
- started: `2026-09-01T07:33:15.272935Z`
- completed: `2026-09-01T07:38:54.500692Z`
- wall-clock interval: `339.23 s`
- predeclared order: `AEDBC`
- models: five
- requests: one cold and one immediate warm request per model
- quality candidates: the five warm responses
- settings: temperature `0`, seed `42`, thinking disabled, context `8,192`,
  generation limit `2,600`, keep-alive `10m`

## Environment gate

The independent process inspection found no active Behat test runner and no
News-App process. The persistent Behat test infrastructure consisted of idle
PHP router workers and a queue consumer; every observed process reported
`0.0%` CPU in both samples. Three long-lived `mnemosyn_mcp.py` helpers also
reported `0.0%` CPU and were not background embedding workers. The resource
gate therefore passed because the auxiliary infrastructure was idle, not
because every process with a Behat or Mnemosyn path was absent.

All five installed model digests matched the frozen comparison plan. Ollama
reported no loaded model at the initial check and remained empty over the
30-second preflight observation. At every model boundary, the harness
explicitly unloaded the prior deployment and confirmed an empty running-model
list before the next cold request. The final deployment was explicitly
unloaded after completion, and Ollama remained empty throughout a 30-second
postflight observation.

## Execution integrity

- comparison status: complete
- technically completed requests: 10 of 10
- `done_reason=stop`: 8
- `done_reason=length`: 2
- judge-bundle artifacts verified: 19 of 19
- hash mismatches: 0
- bundle anonymized: yes
- model identity in bundle: no
- exact deployment tags found in bundle: 0

Four warm candidates produced complete German posts. One warm candidate
exhausted the generation budget and exposed an empty response; this is an
invalid quality outcome, not an infrastructure failure. The blinded warm word
counts are `0`, `415`, `418`, `466` and `495`. All five satisfy the mechanical
maximum-word check, four are nonempty German outputs, and all five are free of
reasoning markup. One complete candidate leaked a technical source-location
label and is subject to the predeclared compliance cap.

The generic deterministic checker reports `heading_pass=false` for every warm
candidate because it was originally designed for structured summaries. This
case requests short LinkedIn paragraphs but does not require a heading, and
the benchmark card defines no heading-related cap. The flag is therefore
inapplicable rather than a candidate failure; it must not affect judgment.

## Blinding state

The private mapping has not been opened. Model-specific latency and throughput
have not been inspected, and no candidate prose has been read. Integrity
verification necessarily established that one opaque candidate is empty. A
recurring failure signature could therefore make its deployment identity
inferable to a judge familiar with earlier runs; random identifiers provide
procedural but not guaranteed cognitive blinding.

All five candidates must be judged independently and any required pairwise
checks frozen before the mapping is opened. These ten requests are Capability
Sweep evidence. They do not estimate latency tails, failure rates or output-
quality distributions.
