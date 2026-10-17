# Multi-Format Capability Sweep v0.1

The 15-cell measured sweep is complete. Results keep the canonical
Track A condition separate from the two real-artifact Track B complete
systems. Each exact configuration has one attempt; this is capability
evidence, not a reliability or latency-distribution estimate.

## Deterministic outcomes by condition

| Condition | Cells | Runtime | Semantic | Strict transport | Checks |
| --- | ---: | ---: | ---: | ---: | ---: |
| `canonical-representation-v0.1` | 5 | 5/5 | 0/5 | 5/5 | 40/55 |
| `mini-multi-format-v0.1` | 5 | 5/5 | 1/5 | 3/5 | 26/55 |
| `pi-multi-format-v0.3` | 5 | 5/5 | 1/5 | 4/5 | 48/55 |

## Deterministic outcomes by model

| Model | Cells | Semantic | Strict transport | Checks |
| --- | ---: | ---: | ---: | ---: |
| `qwen3.6:35b-a3b-mxfp8` | 3 | 0/3 | 2/3 | 25/33 |
| `gemma4:31b-mlx` | 3 | 0/3 | 3/3 | 22/33 |
| `ornith-1.5:35b` | 3 | 0/3 | 2/3 | 18/33 |
| `qwen3.8:27b-mlx` | 3 | 2/3 | 3/3 | 30/33 |
| `muse-glimmer:30b-mlx` | 3 | 0/3 | 2/3 | 19/33 |

## Interpretation boundary

Track A and Track B are not pooled. The Mini and Pi observations are
complete-system outcomes, not a one-factor causal harness comparison.
Turns, tokens and timing are descriptive only. A separate review of
free-text grounding, polarity and usefulness remains mandatory before
deterministic success can be treated as final content acceptance.

Raw responses, document contents, hidden references and absolute paths
are intentionally excluded from this report.
