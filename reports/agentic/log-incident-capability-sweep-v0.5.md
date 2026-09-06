# Agentic Log Incident v0.5 Capability Sweep

This measured sweep compares complete deployed systems. Each cell is
executed once to map capability, not to estimate model reliability.

## Per model and harness

| Harness | Model | Semantic success | Strict transport | Runtime | Median active time |
| --- | --- | ---: | ---: | ---: | ---: |
| Mini | `qwen3.6:35b-a3b-mxfp8` | 0/3 | 3/3 | 3/3 | 57.59 s |
| Mini | `qwen3.8:27b-mlx` | 0/3 | 3/3 | 3/3 | 81.00 s |
| Mini | `muse-glimmer:30b-mlx` | 0/3 | 3/3 | 3/3 | 62.31 s |
| Mini | `ornith-1.5:35b` | 0/3 | 3/3 | 3/3 | 36.98 s |
| Mini | `gemma4:31b-mlx` | 0/3 | 3/3 | 3/3 | 98.08 s |
| Pi 0.84.4 | `qwen3.6:35b-a3b-mxfp8` | 1/3 | 0/3 | 3/3 | 125.09 s |
| Pi 0.84.4 | `qwen3.8:27b-mlx` | 0/3 | 3/3 | 3/3 | 162.36 s |
| Pi 0.84.4 | `muse-glimmer:30b-mlx` | 0/3 | 1/3 | 1/3 | 300.02 s |
| Pi 0.84.4 | `ornith-1.5:35b` | 0/3 | 0/3 | 2/3 | 289.20 s |
| Pi 0.84.4 | `gemma4:31b-mlx` | 0/3 | 3/3 | 3/3 | 239.20 s |

## Per model across both complete systems

| Model | Semantic success | Strict transport | Runtime | Median active time |
| --- | ---: | ---: | ---: | ---: |
| `qwen3.6:35b-a3b-mxfp8` | 1/6 | 3/6 | 6/6 | 97.31 s |
| `qwen3.8:27b-mlx` | 0/6 | 6/6 | 6/6 | 119.47 s |
| `muse-glimmer:30b-mlx` | 0/6 | 4/6 | 4/6 | 140.51 s |
| `ornith-1.5:35b` | 0/6 | 3/6 | 5/6 | 82.56 s |
| `gemma4:31b-mlx` | 0/6 | 6/6 | 6/6 | 180.38 s |

## Per case

| Case | Semantic successes | Strict transport | Runtime-complete outcomes |
| --- | ---: | ---: | ---: |
| Checkout pool regression | 0/10 | 7/10 | 9/10 |
| Retry queue amplification | 1/10 | 8/10 | 10/10 |
| Clock skew partial recovery | 0/10 | 7/10 | 8/10 |

## Interpretation boundaries

- Each system-case configuration has n=1; this is a capability sweep, not a reliability, quality-stochasticity or latency-tail estimate.
- Duration summaries combine heterogeneous cases and are descriptive ranges and medians, not tail percentiles.
- Mini and Pi are complete-system conditions with different prompts, tool protocols and context handling; no one-factor causal harness claim is allowed.
- Historical v0.2, v0.3 and v0.4 attempts and the excluded v0.5 specification confirmation are not pooled with this measured sweep.
- A deterministically normalized report may be a semantic success while strict transport compliance remains false.
- Deterministic structured success is not final quality acceptance; all free-text claims require the separately recorded human grounding review.
- No composite quality-speed score or universal model ranking is calculated.
