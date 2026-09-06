# Agentic Log Incident Capability Sweep v0.2

This report compares complete deployed systems. Each cell was executed once,
so the results describe observed capability rather than reliability.

| Harness | Model | Verified | Runtime | Median active time |
| --- | --- | ---: | ---: | ---: |
| Mini | `qwen3.6:35b-a3b-mxfp8` | 0/3 | 3/3 | 54.11 s |
| Mini | `qwen3.8:27b-mlx` | 0/3 | 3/3 | 85.52 s |
| Mini | `muse-glimmer:30b-mlx` | 0/3 | 3/3 | 68.19 s |
| Mini | `ornith-1.5:35b` | 0/3 | 3/3 | 40.14 s |
| Mini | `gemma4:31b-mlx` | 0/3 | 3/3 | 60.54 s |
| Pi 0.84.4 | `qwen3.6:35b-a3b-mxfp8` | 0/3 | 3/3 | 109.06 s |
| Pi 0.84.4 | `qwen3.8:27b-mlx` | 0/3 | 3/3 | 134.73 s |
| Pi 0.84.4 | `muse-glimmer:30b-mlx` | 0/3 | 3/3 | 254.30 s |
| Pi 0.84.4 | `ornith-1.5:35b` | 0/3 | 3/3 | 256.40 s |
| Pi 0.84.4 | `gemma4:31b-mlx` | 0/3 | 3/3 | 269.96 s |

## Per case

| Case | Verified outcomes | Runtime-complete outcomes |
| --- | ---: | ---: |
| Checkout pool regression | 0/10 | 10/10 |
| Retry queue amplification | 0/10 | 10/10 |
| Clock skew partial recovery | 0/10 | 10/10 |

## Interpretation boundaries

- Each harness-model-case configuration has n=1; this is capability-screen evidence, not a reliability or quality-stochasticity estimate.
- Duration summaries combine heterogeneous cases and are descriptive ranges and medians, not tail percentiles.
- Mini and Pi are complete-system conditions with different prompts, tool protocols and context handling; no one-factor causal harness claim is allowed.
- The excluded qualification smokes are not included in these measured aggregates.
- No composite quality-speed score or universal model ranking is calculated.
