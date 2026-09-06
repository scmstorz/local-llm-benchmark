# Agentic Log Incident v0.4 Specification Confirmation

This excluded confirmation compares complete deployed systems. Each cell was
executed once to audit the corrected specification, not model reliability.

| Harness | Model | Semantic success | Strict transport | Runtime | Median active time |
| --- | --- | ---: | ---: | ---: | ---: |
| Mini | `qwen3.8:27b-mlx` | 1/3 | 3/3 | 3/3 | 82.15 s |
| Pi 0.84.4 | `qwen3.8:27b-mlx` | 0/3 | 1/3 | 3/3 | 138.15 s |

## Per case

| Case | Semantic successes | Strict transport | Runtime-complete outcomes |
| --- | ---: | ---: | ---: |
| Checkout pool regression | 0/2 | 1/2 | 2/2 |
| Retry queue amplification | 0/2 | 1/2 | 2/2 |
| Clock skew partial recovery | 1/2 | 2/2 | 2/2 |

## Interpretation boundaries

- Each system-case configuration has n=1; this is specification-confirmation evidence, not a reliability, capability-ranking or quality-stochasticity estimate.
- Duration summaries combine heterogeneous cases and are descriptive ranges and medians, not tail percentiles.
- Mini and Pi are complete-system conditions with different prompts, tool protocols and context handling; no one-factor causal harness claim is allowed.
- Historical v0.2 attempts are not pooled with this corrected representation.
- A deterministically normalized report may be a semantic success while strict transport compliance remains false.
- No composite quality-speed score or universal model ranking is calculated.
