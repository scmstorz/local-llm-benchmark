# Coding Track B async-cache development smokes v0.2

The same Qwen 3.8 deployment failed the frozen overall contract under
Mini v0.2 and passed it under Pi v0.2. Mini crossed the file-editing boundary
and reached green public tests, but three prose-prefixed JSON actions exhausted
its protocol-error budget and its candidate still failed two hidden checks. Pi
used a failed public test as feedback, repaired the implementation, terminated
normally and passed all twelve deterministic checks.

These are excluded development smokes. They diagnose the two harnesses; they do
not rank them or estimate reliability.

## Frozen scope

| Dimension | Value |
| --- | --- |
| Case | `coding.dev.async-cache-coalescing` v1.0.0 |
| Language / family | JavaScript / feature implementation |
| Deployment | `qwen3.8:27b-mlx` |
| Deployment digest | `5642e97495e1a088883805981563dcdc4a040c2f53388b7a41d1f24d3622cf7e` |
| Harness order | mini-v0.2, then pi-v0.2 |
| Attempts | one cold attempt per harness |
| Retries or repair | none |
| Context | 16,384 tokens |
| Turn output ceiling | 1,600 tokens |
| Total output ceiling | 12,000 tokens |
| Active wall-time ceiling | 900 seconds |
| Normal turn ceiling | none; turns are measured |

The plan and every executable component were hash-frozen before either result.
Both attempts remain excluded from future measured Track B aggregates.

## Layered outcomes

| Harness | Runtime | Agent termination | Final verifier | Overall verified success |
| --- | --- | --- | --- | --- |
| mini-v0.2 | success | invalid: protocol-error limit | fail: 10/12 | false |
| pi-v0.2 | success | valid: normal agent end | pass: 12/12 | true |

The final column is the frozen primary outcome. Agent termination and final-code
verification remain separate because they answer different questions.

## Mini-v0.2

Run `agentic-run-20260902T183410Z-50bb6c87` made eight model calls. Qwen read
three visible files, wrote `src/async-cache.mjs` once and ran the public suite
once. All four public checks passed.

The versioned JSON Schema was present in Ollama's `format` field on every
request. On turns 4, 6 and 8, however, Qwen placed explanatory prose before an
otherwise plausible JSON action. The strict parser deliberately accepts exactly
one JSON object and performs no extraction or repair, so all three responses
became `malformed_action` protocol errors. The third ended the trajectory.

| Metric | Observation |
| --- | ---: |
| Active wall time | 51.84 s |
| Model turns | 8 |
| Protocol errors | 3 |
| Tool calls | 5 |
| File reads | 3 |
| File writes | 1 |
| Public-test runs | 1 |
| First successful public verification | 49.28 s |
| Input tokens | 22,488 |
| Output tokens | 1,848 |
| Final checks | 4/4 public, 6/8 hidden |

Final verification preserved workspace integrity but found two semantic
failures. An invalidated in-flight load could still repopulate the cache, and
`clear()` did not prevent all in-flight keys from repopulating it. Mini
therefore failed both the agent-completion layer and the verifier layer.

This is more informative than the earlier Mini v0.1 PHP smoke: the harness now
crossed its transport boundary often enough to read, edit and test. It remains
brittle for this exact model/runtime/schema combination because schema-aware
generation did not consistently yield a prose-free action.

## Pi-v0.2

Run `pi-agentic-run-20260902T184008Z-3b9f1e8c` used pinned
`@earendil-works/pi-coding-agent@0.84.4`. Its run-specific
`pi-macos-seatbelt-v0.1` profile passed all eleven executable acceptance checks
before inference. Pi and its children could access only the isolated workspace,
the pinned executable set and local Ollama; the hidden verifier was unavailable
until the agent process exited.

Pi completed normally in six turns. It made eight tool calls, read four files,
wrote `src/async-cache.mjs` once and ran the public suite twice. The first
public run failed. The second passed after 154.36 seconds, and Pi then emitted a
valid final response. Separate verification passed 4/4 public and 8/8 hidden
checks with no scope or integrity violation.

| Metric | Observation |
| --- | ---: |
| Active wall time | 195.28 s |
| Model turns | 6 |
| Protocol errors | 0 |
| Tool calls | 8 |
| Failed tool calls | 1 failed public test |
| File reads | 4 |
| File writes | 1 |
| Public-test runs | 2 |
| First successful public verification | 154.36 s |
| Input tokens | 42,012 |
| Output tokens | 7,751 |
| Final checks | 4/4 public, 8/8 hidden |

Unlike the earlier Pi v0.1 PHP smoke, this run was not cut off by an arbitrary
turn boundary. The six observed turns are retained as trajectory evidence, but
they do not determine success.

## Resource isolation

Before Mini, the exact Qwen digest was verified and Ollama remained empty for a
full 30-second observation window. Qwen was explicitly unloaded after Mini;
Ollama again stayed empty for 30 seconds before Pi. The same unload and
30-second empty observation completed the postflight. No unexpected model or
known Ollama-using application confounded either attempt.

## What the smoke establishes

The result supports four bounded statements:

1. Removing the normal turn limit fixed the artificial v0.1 stopping boundary;
   neither v0.2 outcome was caused by turn count.
2. Qwen plus Mini v0.2 did not reliably obey the strict action protocol and its
   final candidate missed two hidden concurrency requirements.
3. Qwen plus Pi v0.2 completed the same task with valid termination and full
   deterministic verification.
4. Public-green code was not necessarily task-complete; hidden verification
   materially changed the Mini result.

One excluded attempt per harness does **not** establish a general Pi advantage.
The trajectories did different work, so their wall times cannot support a
speed ranking. Reliability, stochastic quality and latency tails require the
separate repeated-run studies already planned.

## Protocol consequence

The observed runs will not be rerun or repaired. Pi v0.2 is viable for a later
measured Track B plan. Mini's transport boundary needs a separately versioned
diagnostic before that freeze: determine why this exact Ollama deployment emits
leading prose despite receiving the schema, then decide whether the next Mini
version should change schema shape, model configuration or protocol. Any such
change creates new evidence; it cannot retroactively alter this smoke.
