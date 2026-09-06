# Track B Pi v0.3 Capability Sweep

## Outcome

The frozen 15-run sweep completed with **9/15 verified successful outcomes**. `qwen3.8:27b-mlx` is the only model that passes all three cases in this single-run screen.

| Model | PHP | JavaScript | Python | Verified | Verifier | Median active time |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| `qwen3.6:35b-a3b-mxfp8` | PASS (106.1s) | FAIL (192.7s) | FAIL (535.9s) | 1/3 | 1/3 | 192.7s |
| `qwen3.8:27b-mlx` | PASS (95.8s) | PASS (147.3s) | PASS (195.5s) | 3/3 | 3/3 | 147.3s |
| `muse-glimmer:30b-mlx` | PASS (371.0s) | FAIL (367.1s) | FAIL (227.7s) | 1/3 | 1/3 | 367.1s |
| `ornith-1.5:35b` | PASS (87.3s) | FAIL (900.0s) | PASS (780.3s) | 2/3 | 3/3 | 780.3s |
| `gemma4:31b-mlx` | PASS (154.9s) | FAIL (187.1s) | PASS (255.8s) | 2/3 | 2/3 | 187.1s |

## Results by case

| Case | Verified | Verifier | Median | Range |
| --- | ---: | ---: | ---: | ---: |
| PHP payment migration | 5/5 | 5/5 | 106.1s | 87.3–371.0s |
| JavaScript async cache | 1/5 | 2/5 | 192.7s | 147.3–900.0s |
| Python pagination guard | 3/5 | 3/5 | 255.8s | 195.5–780.3s |

## Main observations

- qwen3.8:27b-mlx is the only deployment with verified success on all three cases in this single-run screen.
- All five deployments solve the PHP case; only qwen3.8:27b-mlx reaches verified success on the JavaScript case.
- Three deployments solve Python, but active duration ranges from about 195 seconds to about 780 seconds among those successes.
- ornith-1.5:35b leaves a fully verifier-passing JavaScript workspace when the 900-second active task limit terminates the agent, so the user-relevant outcome remains a failure.
- muse-glimmer:30b-mlx succeeds on PHP but ends with an invalid model stream on both JavaScript and Python, showing that Track A text quality does not imply stable agentic system behavior.

The Ornith JavaScript run is deliberately a failure despite a green final verifier: the workspace is verifier-passing when the preregistered 900-second limit terminates the still-running agent. This distinction is the intended meaning of verified success.

Qwen 3.6 on Python reached 59 turns and 30 public test runs before the emergency safeguard terminated the trajectory. Its final workspace also failed verification. The raw outcome labels the red public tests as the failure, while the trajectory carries the more causally prior safeguard termination; both facts remain preserved.

## Methodological limits

- Each model-task configuration has n=1. These are Capability Sweep observations, not reliability probabilities or performance distributions.
- Median and range values summarize three heterogeneous per-model runs or five per-case runs; they are descriptive and not tail estimates.
- The host was unavailable for part of the sweep. Per-run active monotonic duration is reported; total sweep elapsed time is not treated as performance evidence.
- The raw Qwen 3.6 Python outcome prioritizes its red public verifier, while its trajectory records the terminal emergency test-run safeguard. The public report preserves both and uses the explicit terminal condition as the effective failure.
- No composite quality-speed score or universal model ranking is inferred from three heterogeneous coding cases.

## Provenance

- Sweep: `pi-v03-sweep-20260904T154510Z-eb3b2311`
- Plan: `track-b-pi-capability-sweep-v0.3`
- Ollama: `0.33.2`
- Pi: `0.84.4`
- Execution commit: `fe3c8da08237da67c1a643203049abc1a04ad891`
- Sweep SHA-256: `aa06a0c646eb25a9616289f6ab6a6376c9e388b0f29f8c894445c2a964d2cc44`
