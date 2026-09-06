# Track B Mini v0.3 Qwen 3.8 JavaScript Smoke

## Outcome

The one preregistered, excluded smoke completed with a technically valid Mini
v0.3 trajectory, but it did **not** reach verified task success.

| Dimension | Result |
| --- | --- |
| Runtime completed | yes |
| Valid Mini `finish` action | yes |
| Protocol errors | 0 |
| Public tests | 4/4 passed |
| Hidden checks | 6/8 passed |
| Verified success | no |
| Failure | `hidden_tests_failed` |
| Active model + tool time | 50.80 s |
| Final verification time | 0.11 s, reported separately |

The candidate handled caching, concurrent-miss coalescing, rejected and
synchronously throwing loaders, and several TTL details. It missed both hidden
in-flight invalidation behaviors: invalidating one key and clearing all keys
while loader promises were unresolved.

## Why the technical gate passes

The smoke was designed to qualify the live execution machinery, not to promote
its result into the measured cohort. It required a complete interpretable
terminal outcome, no adapter or orchestration defect, and a machine-classified
failure if the task was not solved. All three conditions hold:

- Qwen emitted six schema-valid actions and ended with a valid `finish`.
- Model calls remained separate from sandboxed tool and verifier execution.
- The deterministic verifier identified a task failure rather than an
  infrastructure, transport or harness failure.

The later five-model by three-task Mini sweep may therefore be frozen. This
smoke remains excluded and will not be reused as Qwen's measured JavaScript
cell.

## Resource control

Blog-Read-O-Matic and News-App were stopped. Their resident embedding model was
explicitly unloaded. Ollama reported no loaded model at both ends of the frozen
30-second observation window (21:28:08–21:28:38 UTC). Qwen was unloaded after
the run and the postflight model list was empty.

## Provenance

- Plan: `mini-qwen38-js-development-smoke-v0.3.1`
- Run: `mini-v03-agentic-run-20260904T212846Z-038354d8`
- Harness: `mini-v0.3`
- Model: `qwen3.8:27b-mlx`
- Ollama: `0.33.2`
- Execution commit: `4fb087fa3ed49234c5433e2919df612c1b91ed24`
- Raw run SHA-256: `0b99da77ca231144b650304102fd8bcf21b9573e041f8d482e36b50cebec4f47`

The public report contains no raw model response, candidate source, test output
or absolute local path.
