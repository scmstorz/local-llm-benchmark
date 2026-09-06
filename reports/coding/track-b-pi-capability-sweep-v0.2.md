# Coding Track B Pi capability sweep v0.2

The frozen eight-model by two-case Pi sweep completed all 16 planned
configurations under Ollama 0.33.2. Six systems reached a valid agent end
and passed all 12 deterministic checks. The remaining ten outcomes must
not be collapsed into ten model-capability failures: four are inconclusive
transport or standby observations, while six are bounded or verified task
failures.

## Frozen scope

| Dimension | Value |
| --- | --- |
| Harness | `pi-v0.2` with `@earendil-works/pi-coding-agent@0.84.4` |
| Runtime | Ollama 0.33.2 |
| Deployments × cases | 8 × 2 = 16 |
| Attempts | one per configuration; no retry |
| Active wall-time ceiling | 900 s |
| Total output ceiling | 12,000 tokens |
| Normal turn ceiling | none; turns are measured |

## Outcome matrix

| # | Model | Case | Verified | Diagnostic outcome | Checks | Active time | Turns / tools |
| ---: | --- | --- | :---: | --- | ---: | ---: | ---: |
| 1 | `qwen3.6:35b-a3b-mxfp8` | PHP | yes | verified success | 4/4 + 8/8 | 88.02 s | 14 / 24 |
| 2 | `qwen3.8:27b-mlx` | PHP | yes | verified success | 4/4 + 8/8 | 73.20 s | 5 / 15 |
| 3 | `gpt-oss:20b` | PHP | no | active-time budget | 4/4 + 8/8 | 900.02 s | 18 / 16 |
| 4 | `muse-glimmer:30b-mlx` | PHP | no | provider request timeout (inconclusive) | 2/4 + 3/8 | 83.19 s | 5 / 14 |
| 5 | `ornith-1.5:35b` | PHP | yes | verified success | 4/4 + 8/8 | 111.09 s | 14 / 22 |
| 6 | `granite4.2:30b` | PHP | yes | verified success | 4/4 + 8/8 | 360.82 s | 10 / 17 |
| 7 | `nemotron-3.5-lightning:30b-mlx` | PHP | yes | verified success | 4/4 + 8/8 | 96.81 s | 14 / 29 |
| 8 | `gemma4:31b-mlx` | PHP | yes | verified success | 4/4 + 8/8 | 156.26 s | 14 / 13 |
| 9 | `gemma4:31b-mlx` | JavaScript | no | hidden-test failure | 4/4 + 7/8 | 240.42 s | 7 / 6 |
| 10 | `nemotron-3.5-lightning:30b-mlx` | JavaScript | no | output-token budget | 3/4 + 5/8 | 352.13 s | 7 / 10 |
| 11 | `granite4.2:30b` | JavaScript | no | output-token budget | 4/4 + 6/8 | 774.52 s | 19 / 18 |
| 12 | `ornith-1.5:35b` | JavaScript | no | output-token budget | 3/4 + 7/8 | 425.15 s | 5 / 7 |
| 13 | `muse-glimmer:30b-mlx` | JavaScript | no | active-time budget | 3/4 + 5/8 | 900.03 s | 3 / 5 |
| 14 | `gpt-oss:20b` | JavaScript | no | provider stream incomplete (inconclusive) | 3/4 + 5/8 | 167.26 s | 8 / 7 |
| 15 | `qwen3.8:27b-mlx` | JavaScript | no | provider request timeout (inconclusive) | 3/4 + 5/8 | 30.77 s | 1 / 0 |
| 16 | `qwen3.6:35b-a3b-mxfp8` | JavaScript | no | standby timing confound (inconclusive) | 3/4 + 5/8 | 31.90 s | 2 / 4 |

## What is conclusive

The primary frozen outcome is **6/16 verified successes**.
Each success is strong positive evidence for that exact model, runtime,
task and Pi configuration. PHP accounted for all six successes. GPT-OSS
also left PHP code that passed 12/12 checks, but it never terminated within
the 900-second budget; it is a bounded overall failure, not a success.

The JavaScript case produced one clean task-level near miss: Gemma ended
normally, passed all public checks and 7/8 hidden checks. Nemotron, Granite
and Ornith exhausted the output budget. Glimmer exhausted active wall time.
Those five are valid bounded negative outcomes for the tested system.

## What is inconclusive

Glimmer/PHP and Qwen 3.8/JavaScript encountered provider request timeouts;
GPT-OSS/JavaScript ended with an incomplete provider stream. The adapter
recorded a 300-second request timeout but did not explicitly pass it into
Pi's provider settings, so these outcomes cannot support a capability claim.

Qwen 3.6/JavaScript was aborted by the extension's wall-clock check after
notebook standby, although the parent measured only 31.90 active seconds.
That result is also inconclusive. Raw files remain immutable; this report
adds a derived diagnostic taxonomy rather than rewriting history.

## Why this is Track B

The experimental unit is the deployed system, not the model alone:
`task × model × Ollama × pinned Pi × tools × budgets × verifier × run`.
Tool behavior, agent termination and transport compatibility therefore count
alongside final-code verification. Track A results remain separate.

## Interpretation limits

Every configuration has `n=1`. Times, turns and tool counts are descriptive
trajectory observations, not performance distributions or reliability
estimates. No P90/P95 claim and no universal ranking is justified. The earlier
interrupted Ollama 0.32.15 sweep is retained separately and is not pooled.

## Next correction

Candidate `pi-v0.3` requires an explicit 300-second provider timeout and makes
the parent's monotonic timer the sole 900-second authority. It also records
trajectory tokens and turns without using either as a normal abort condition.
Its separate configuration builder and policy extension are implemented without
modifying the frozen v0.2 adapter. The live adapter must still pass no-inference,
Seatbelt and transport qualification and be frozen as a new experimental
configuration before any rerun. The v0.2 observations will not be repaired or
silently repeated.
