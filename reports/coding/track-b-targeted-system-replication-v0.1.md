# Track B Targeted System Replication v0.1

## Outcome

The frozen follow-up completed all **8 fresh runs**. Together with the four explicitly identified baseline observations, the report contains **12 planned observations** and 5 verified successes.

| Model and case | System | Baseline | Fresh 2 | Fresh 3 | Pattern | Active duration, all outcomes |
| --- | --- | ---: | ---: | ---: | --- | --- |
| `qwen3.8:27b-mlx` / JavaScript async cache | `pi-v0.3` | PASS | FAIL | PASS | `mixed_outcomes` | median 251.09s; range 147.27–312.97s |
| `qwen3.8:27b-mlx` / JavaScript async cache | `mini-v0.3` | FAIL | FAIL | FAIL | `consistent_failure` | median 40.91s; range 40.28–44.86s |
| `qwen3.6:35b-a3b-mxfp8` / Python pagination guard | `pi-v0.3` | FAIL | FAIL | FAIL | `consistent_failure` | median 900.02s; range 535.92–900.04s |
| `qwen3.6:35b-a3b-mxfp8` / Python pagination guard | `mini-v0.3` | PASS | PASS | PASS | `consistent_success` | median 54.59s; range 52.81–81.98s |

The counts are descriptive outcomes, not estimated success probabilities. With `n=3` per system cell, the report intentionally omits tail percentiles.

## Individual observations

| Model and case | System | Origin | Result | Active | Turns | Tools | Failed tools | Failure |
| --- | --- | --- | ---: | ---: | ---: | ---: | ---: | --- |
| `qwen3.8:27b-mlx` / JavaScript async cache | `pi-v0.3` | baseline | PASS | 147.27s | 5 | 7 | 0 | `—` |
| `qwen3.8:27b-mlx` / JavaScript async cache | `pi-v0.3` | fresh 2 | FAIL | 251.09s | 5 | 8 | 0 | `hidden_tests_failed` |
| `qwen3.8:27b-mlx` / JavaScript async cache | `pi-v0.3` | fresh 3 | PASS | 312.97s | 7 | 10 | 2 | `—` |
| `qwen3.8:27b-mlx` / JavaScript async cache | `mini-v0.3` | baseline | FAIL | 40.91s | 7 | 6 | 0 | `hidden_tests_failed` |
| `qwen3.8:27b-mlx` / JavaScript async cache | `mini-v0.3` | fresh 2 | FAIL | 40.28s | 7 | 6 | 0 | `hidden_tests_failed` |
| `qwen3.8:27b-mlx` / JavaScript async cache | `mini-v0.3` | fresh 3 | FAIL | 44.86s | 6 | 5 | 0 | `hidden_tests_failed` |
| `qwen3.6:35b-a3b-mxfp8` / Python pagination guard | `pi-v0.3` | baseline | FAIL | 535.92s | 59 | 63 | 51 | `emergency_operation_safeguard_exceeded` |
| `qwen3.6:35b-a3b-mxfp8` / Python pagination guard | `pi-v0.3` | fresh 2 | FAIL | 900.02s | 104 | 107 | 91 | `maximum_active_wall_time_exceeded` |
| `qwen3.6:35b-a3b-mxfp8` / Python pagination guard | `pi-v0.3` | fresh 3 | FAIL | 900.04s | 84 | 87 | 78 | `maximum_active_wall_time_exceeded` |
| `qwen3.6:35b-a3b-mxfp8` / Python pagination guard | `mini-v0.3` | baseline | PASS | 81.98s | 13 | 12 | 1 | `—` |
| `qwen3.6:35b-a3b-mxfp8` / Python pagination guard | `mini-v0.3` | fresh 2 | PASS | 54.59s | 13 | 12 | 3 | `—` |
| `qwen3.6:35b-a3b-mxfp8` / Python pagination guard | `mini-v0.3` | fresh 3 | PASS | 52.81s | 13 | 12 | 1 | `—` |

## Main observations

- Qwen 3.8 on the JavaScript cache case succeeded in 2/3 Pi observations and 0/3 Mini observations; Pi's outcomes were mixed while Mini failed consistently.
- Qwen 3.6 on the Python pagination case succeeded in 0/3 Pi observations and 3/3 Mini observations, reproducing the baseline reversal twice in each direction.
- The two selected cross-system differences point in opposite directions. The evidence therefore rejects a simple claim that either harness is uniformly better.
- Pi/Qwen 3.6 reached an emergency operation safeguard once and the 900-second active-time boundary twice; Mini/Qwen 3.6 completed successfully in all three observations with 13 turns each.
- Mini/Qwen 3.8 finished quickly in all three observations but consistently failed hidden verification. Fast termination did not imply a verified outcome.

## Methodological limits

- The two model-task cells were selected after inspecting the original paired screen. This is targeted follow-up evidence, not a confirmatory random sample of tasks.
- Each system cell has only three descriptive observations. Counts are not success-probability estimates, and no P90, P95, P99 or statistical-significance claim is reported.
- The baseline remains explicitly separate from the two fresh repetitions even though deployment, task, runtime, harness and inference identities match.
- Pi and Mini differ in prompts, action protocols, tool implementations, context accumulation and error handling. Outcomes compare complete deployed systems and do not isolate a causal harness effect.
- Durations for failed runs remain visible but are not equivalent to time-to-success. Successful-only duration summaries are reported separately.
- One interrupted Pi attempt caused by host sleep or process interruption is preserved in raw evidence and excluded from all twelve planned observations.
- No composite score or universal model or harness ranking is calculated.

## Provenance

- Frozen plan: `track-b-targeted-system-replication-v0.1` (`26fdfb2af121175675f8ac24f9b9e5bdbba86a63512665e13327bf0699eda2ee`)
- Completed local study: `track-b-replication-20260905T065124Z-cbc09fb5` (`f29ed1aaa5019f61ff647024bbcdd8982e88f439dc0a2cbe6076ddb71306cc64`)
- Pi baseline: `track-b-pi-capability-sweep-v0.3`
- Mini baseline: `track-b-mini-capability-sweep-v0.3`
