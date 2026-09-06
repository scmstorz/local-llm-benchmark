# Track B Pi v0.3 vs Mini v0.3 System Comparison

## Outcome

Across 15 matched model-task cells, Pi produced **9 verified successes** and Mini produced **6**. The binary outcomes agreed in 10/15 cells.

| Model | Pi verified | Mini verified | Agreement |
| --- | ---: | ---: | ---: |
| `qwen3.6:35b-a3b-mxfp8` | 1/3 | 2/3 | 2/3 |
| `qwen3.8:27b-mlx` | 3/3 | 1/3 | 1/3 |
| `muse-glimmer:30b-mlx` | 1/3 | 1/3 | 3/3 |
| `ornith-1.5:35b` | 2/3 | 1/3 | 2/3 |
| `gemma4:31b-mlx` | 2/3 | 1/3 | 2/3 |

## Results by case

| Case | Pi verified | Mini verified | Agreement |
| --- | ---: | ---: | ---: |
| PHP payment migration | 5/5 | 4/5 | 4/5 |
| JavaScript async cache | 1/5 | 0/5 | 4/5 |
| Python pagination guard | 3/5 | 2/5 | 2/5 |

## Paired cells

| Model | Case | Pi | Mini | Relation |
| --- | --- | ---: | ---: | --- |
| `qwen3.6:35b-a3b-mxfp8` | PHP payment migration | PASS (106.1s) | PASS (105.8s) | `both_success` |
| `qwen3.8:27b-mlx` | JavaScript async cache | PASS (147.3s) | FAIL (40.9s) | `pi_only_success` |
| `muse-glimmer:30b-mlx` | Python pagination guard | FAIL (227.7s) | FAIL (75.0s) | `both_failure` |
| `ornith-1.5:35b` | PHP payment migration | PASS (87.3s) | PASS (45.3s) | `both_success` |
| `gemma4:31b-mlx` | JavaScript async cache | FAIL (187.1s) | FAIL (51.6s) | `both_failure` |
| `muse-glimmer:30b-mlx` | JavaScript async cache | FAIL (367.1s) | FAIL (137.9s) | `both_failure` |
| `ornith-1.5:35b` | Python pagination guard | PASS (780.3s) | FAIL (21.9s) | `pi_only_success` |
| `gemma4:31b-mlx` | PHP payment migration | PASS (154.9s) | FAIL (904.0s) | `pi_only_success` |
| `qwen3.6:35b-a3b-mxfp8` | JavaScript async cache | FAIL (192.7s) | FAIL (940.9s) | `both_failure` |
| `qwen3.8:27b-mlx` | Python pagination guard | PASS (195.5s) | FAIL (147.5s) | `pi_only_success` |
| `gemma4:31b-mlx` | Python pagination guard | PASS (255.8s) | PASS (590.6s) | `both_success` |
| `qwen3.6:35b-a3b-mxfp8` | Python pagination guard | FAIL (535.9s) | PASS (82.0s) | `mini_only_success` |
| `qwen3.8:27b-mlx` | PHP payment migration | PASS (95.8s) | PASS (132.5s) | `both_success` |
| `muse-glimmer:30b-mlx` | PHP payment migration | PASS (371.0s) | PASS (210.0s) | `both_success` |
| `ornith-1.5:35b` | JavaScript async cache | FAIL (900.0s) | FAIL (146.7s) | `both_failure` |

## Main observations

- Pi produced 9/15 verified outcomes; Mini produced 6/15.
- The systems agreed on verified success or failure in 10/15 matched cells.
- Pi alone succeeded in 4 cells; Mini alone succeeded in 1 cell.
- Both systems succeeded in 5 cells and both failed in 5 cells.

## Methodological limits

- Every matched system configuration has n=1, so outcome flips may reflect stochasticity and are not reliability estimates.
- Pi v0.3 and Mini v0.3 differ in prompts, protocol, tool implementations, context accumulation and error handling. This is a complete-system comparison, not an isolated causal estimate of harness quality.
- Active duration includes model and tool time, excludes host standby gaps, and is not adjusted for success. Duration deltas must be interpreted together with verified outcomes.
- Token and turn counts are system-level trajectory measurements whose semantics can differ across harnesses.
- No composite score or universal ranking is calculated.

## Provenance

- Pi report: `track-b-pi-capability-sweep-v0.3` (`95ab40cdf0b041e8ecf3471bb17adb82825c7c7833dd241f6c046028183db6e2`)
- Mini report: `track-b-mini-capability-sweep-v0.3` (`38e79229401af6aaa2216d0a381f2de43355d0611ceeb10f1e63effb831dfa85`)
