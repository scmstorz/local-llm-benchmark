# Track B Mini v0.3 Capability Sweep

## Outcome

The frozen 15-run sweep completed with **6/15 verified successful outcomes**.

| Model | PHP | JavaScript | Python | Verified | Verifier | Median active time |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| `qwen3.6:35b-a3b-mxfp8` | PASS (105.8s) | FAIL (940.9s) | PASS (82.0s) | 2/3 | 2/3 | 105.8s |
| `qwen3.8:27b-mlx` | PASS (132.5s) | FAIL (40.9s) | FAIL (147.5s) | 1/3 | 1/3 | 132.5s |
| `muse-glimmer:30b-mlx` | PASS (210.0s) | FAIL (137.9s) | FAIL (75.0s) | 1/3 | 1/3 | 137.9s |
| `ornith-1.5:35b` | PASS (45.3s) | FAIL (146.7s) | FAIL (21.9s) | 1/3 | 1/3 | 45.3s |
| `gemma4:31b-mlx` | FAIL (904.0s) | FAIL (51.6s) | PASS (590.6s) | 1/3 | 1/3 | 590.6s |

## Results by case

| Case | Verified | Verifier | Median | Range |
| --- | ---: | ---: | ---: | ---: |
| PHP payment migration | 4/5 | 4/5 | 132.5s | 45.3–904.0s |
| JavaScript async cache | 0/5 | 0/5 | 137.9s | 40.9–940.9s |
| Python pagination guard | 2/5 | 2/5 | 82.0s | 21.9–590.6s |

## Main observations

- Highest observed coverage is 2/3 for qwen3.6:35b-a3b-mxfp8.
- Highest case success is 4/5 on PHP payment migration.
- Lowest case success is 0/5 on JavaScript async cache.
- Model, tool and final-verification time remain separate; active duration is only model plus tool time.

## Methodological limits

- Each model-task configuration has n=1. These are Capability Sweep observations, not reliability probabilities or performance distributions.
- Median and range values summarize heterogeneous tasks or models; they are descriptive and not tail estimates.
- Pi v0.3 and Mini v0.3 are complete-system deployments with different prompts, protocols, tool implementations, context accumulation and error handling. Cross-harness differences are not one-factor causal effects.
- No composite quality-speed score or universal model ranking is inferred from three coding cases.
- Raw failure classifications are preserved. Known active-time classification discrepancies are resolved only in the public report and must be fixed in a future harness version, not by mutating the frozen adapter used for this sweep.

## Provenance

- Sweep: `mini-v03-sweep-20260904T213634Z-a652de35`
- Plan: `track-b-mini-capability-sweep-v0.3`
- Ollama: `0.33.2`
- Execution commit: `f31382bf0cae6da95973a6e8a5997ef1170ccb42`
- Sweep SHA-256: `bd9246ce1c3aefbd902679ee7b493192e5164aad262d31df3a89edd5d4049317`
