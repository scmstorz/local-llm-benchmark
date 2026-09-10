# Performance and Reliability Study v0.1

This report separates natural-output latency from a controlled 256-token
decode workload. Warm-up runs and model load are excluded from steady-state
distributions. Reliability counts every planned measured attempt.

| Workload | Model | Technical | Output contract | Wall P50 | Wall P90 | First content P50 | Decode tok/s P50 |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: |
| controlled_decode | `ornith-1.5:35b` | 20/20 | 20/20 | 2.83 s | 3.16 s | 0.05 s | 92.21 |
| natural_output | `ornith-1.5:35b` | 20/20 | 20/20 | 11.95 s | 12.59 s | 0.05 s | 92.82 |
| controlled_decode | `qwen3.8:27b-mlx` | 20/20 | 20/20 | 3.63 s | 4.82 s | 0.14 s | 71.75 |
| natural_output | `qwen3.8:27b-mlx` | 20/20 | 20/20 | 29.25 s | 128.81 s | 0.09 s | 43.02 |

P90 is shown only when at least 20 valid measured observations remain.
P95 and P99 are not reported at this sample size. Natural-output timings
include answer-length variation and must not be read as pure runtime speed.
No semantic quality judgment or composite score is part of this study.
