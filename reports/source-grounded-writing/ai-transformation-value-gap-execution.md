# AI transformation value gap — execution report

## Evidence status

This report records execution integrity only. It deliberately omits the private
candidate-to-model mapping, model-specific performance and candidate prose.
Quality judgment and unblinding are complete. See the companion
[`quality report`](ai-transformation-value-gap-quality.md). This execution
section preserves the state and claims available before judgment.

## Comparison

- comparison ID: `comparison-20260830T172156Z-450bbffe`
- case: `source_grounded_writing.dev.ai-transformation-value-gap`
- harness commit: `32fc48d695bbffdc42ee4e7cd94e398b91d23030`
- Ollama version: `0.32.15`
- started: `2026-08-30T17:21:56.024836Z`
- completed: `2026-08-30T17:27:11.736533Z`
- predeclared order: `DBCEA`
- models: five
- requests: one cold and one immediate warm request per model
- quality candidates: the five warm responses
- settings: temperature `0`, seed `42`, thinking disabled, context `8,192`,
  generation limit `2,600`, keep-alive `10m`

## Environment gate

No News-App process or Mnemosyn application worker was active. Three
`mnemosyn_mcp.py` helpers belonged to other interactive sessions and were not
the embedding worker. Ollama initially retained
`nomic-embed-text-v2-moe:latest`; it was explicitly unloaded and did not
reappear during a 30-second observation window. Ollama was empty immediately
before the comparison.

The first CLI invocation was blocked locally before reaching Ollama by the
Codex filesystem/network sandbox. It generated no candidate. The authorized
invocation then executed the unchanged committed plan.

At every observed boundary only the expected candidate deployment was loaded.
The harness reported an empty model list after every explicit inter-model
unload. The final Qwen deployment was unloaded after completion, and Ollama
remained empty throughout a 30-second postflight observation.

## Execution integrity

- comparison status: complete
- technically completed requests: 10 of 10
- `done_reason=stop`: 8
- `done_reason=length`: 2
- judge-bundle artifacts verified: 19 of 19
- hash mismatches: 0
- bundle anonymized: yes
- model identity in bundle: no

Four warm candidates produced complete German posts. One warm candidate
exhausted the generation budget and exposed no visible response; it is an
invalid quality outcome, not an infrastructure failure. The blinded warm word
counts are `0`, `387`, `424`, `448` and `485`. One complete candidate leaked a
technical source-location label and is subject to the predeclared compliance
cap.

The generic deterministic checker reports `heading_pass=false` for every warm
candidate because it was originally designed for structured summaries. This
case requests short LinkedIn paragraphs but does not require a heading, and
the benchmark card defines no heading-related cap. The flag is therefore
inapplicable rather than a candidate failure; it must not affect judgment.

## Blinding state

The private mapping has not been opened. Model-specific latency and throughput
have not been inspected. The interactive judge may still recognize recurring
failure patterns from earlier cases, so random identifiers provide procedural
but not guaranteed cognitive blinding. All five candidates must be judged and
any required pairwise checks frozen before the mapping is opened.

These ten requests are Capability Sweep evidence. They do not estimate latency
tails, failure rates or output-quality distributions.
