# Pagination cycle guard — Track A comparison v1

## Result

None of the five local deployments produced a verified successful outcome
under the frozen direct unified-diff contract.

| Order | Deployment | Outcome | Failure | Cold wall time | Output tokens |
| ---: | --- | --- | --- | ---: | ---: |
| 1 | `gpt-oss:20b` | FAIL | Empty visible output after length termination | 39.71 s | 3,000 |
| 2 | `qwen3.6:35b-a3b-mxfp8` | FAIL | Patch application | 31.53 s | 402 |
| 3 | `qwen3.8:27b-mlx` | FAIL | Length termination and corrupt patch | 58.44 s | 3,000 |
| 4 | `ornith-1.5:35b` | FAIL | Patch application | 15.73 s | 441 |
| 5 | `muse-glimmer:30b-mlx` | FAIL | Patch application | 61.72 s | 1,820 |

All five inference requests completed technically. Four produced visible patch
text, but no patch applied to the frozen fixture. Consequently no public or
hidden candidate test suite ran, and time to verified success is undefined.
The five attempt wall times sum to 207.12 seconds.

## Candidate diagnostics

- GPT-OSS consumed its full generation budget in hidden reasoning and returned
  no visible artifact.
- Qwen 3.6 emitted a patch against incorrect source context. Its proposed code
  also referenced `seen_cursors` without defining it.
- Qwen 3.8 proposed broadly relevant logic but entered a long added-blank-line
  loop, exhausted the output budget and ended with a corrupt patch.
- Ornith reproduced its earlier smoke response byte for byte. The malformed
  hunk header and incorrect import context were therefore deterministic under
  the fixed settings, not a one-off transport error.
- Glimmer emitted an invalid hunk body and also checked the current cursor
  instead of `next_cursor` for terminality after a fetch.

These diagnostics do not award partial credit. They explain the failed
artifacts while `verified_success` remains the primary outcome.

## Environment integrity

All five installed model digests matched the frozen plan. No News-App or
user-facing Mnemosyn worker was observed. Three Mnemosyn MCP helpers remained
idle. A persistent Behat queue consumer accumulated only 0.03 CPU seconds over
a ten-second observation and was treated as idle infrastructure rather than an
active test workload.

Ollama remained empty during the 30-second preflight. Each candidate was
explicitly unloaded after its attempt, no unexpected model appeared, and the
30-second postflight also remained empty.

## Methodological finding

The formal result is valid: no tested deployment satisfied the requested
single-turn unified-diff contract. But the comparison also exposed a floor
effect. Patch formatting prevented the deterministic tests from measuring the
deeper repair capability of every visible candidate.

The benchmark must not repair these outputs retrospectively or reinterpret
them as passes. Instead, v1 remains preserved and a separate contract version
should be preregistered. A structured whole-file replacement format is the
leading option: the controller can validate paths and write exact candidate
content into the disposable fixture without asking the model to calculate diff
hunk ranges. Public and hidden tests can then measure the code rather than the
model's ability to serialize a Git patch.

That new version would answer a different question. Track A v1 asks whether a
model can produce a directly applicable patch. A whole-file variant would ask
whether it can produce correct replacement code under the same no-tool,
single-turn conditions. Both results should remain visible and must not be
pooled as if the harness were unchanged.

## Interpretation limit

This is one development task with one post-freeze attempt per deployment. It
does not establish general coding superiority, reliability, latency tails or a
minimum sufficient model. Cold timing remains diagnostic only because none of
the attempts produced a verified successful outcome.
