# September 2026 Model Cohort — Execution Record

Date: 2026-09-03

Suite: `personal-capability-suite-v0.3`

Suite hash: `7ebdfd4a48a4361d10018d03676f6b19fbb5bfae43c03b4ea0c9c2a7d7ac0a80`

Status: all 90 planned Ollama requests complete

## Frozen method

Each of the three preregistered deployments ran all 15 cases in the immutable
Suite v0.3. Every case had one explicit cold request after unloading all Ollama
models and one immediate warm request. The warm response was the predeclared
quality candidate. Settings stayed fixed at temperature 0, seed 42,
`num_predict=2600`, `think=false`, a ten-minute keep-alive and the case-specific
context requirement. No answer was repaired or retried after inspection.

The resource gate observed no loaded Ollama model before the uninterrupted
Nemotron and Gemma sweeps. Known background application processes existed but
were idle and showed no CPU activity. The runner recorded only the expected
candidate deployment during each sweep and unloaded it after completion.

## Execution outcome

| Order | Deployment | Sweep | Complete cases | Runtime failures | Measured request wall sum | Elapsed sweep |
| ---: | --- | --- | ---: | ---: | ---: | ---: |
| 1 | `granite4.2:30b` | `sweep-20260902T202515Z-0239c5cf` | 15 / 15 | 0 | 7,436.37 s | 38,745.36 s |
| 2 | `nemotron-3.5-lightning:30b-mlx` | `sweep-20260903T071312Z-18ca6634` | 15 / 15 | 0 | 530.04 s | 534.02 s |
| 3 | `gemma4:31b-mlx` | `sweep-20260903T072332Z-b3b47142` | 15 / 15 | 0 | 1,512.91 s | 1,518.95 s |

`Runtime failures = 0` means Ollama returned a terminal response for all cold
and warm requests. It does not mean that all candidate outputs were complete,
format-compliant or semantically successful.

## Warm-run performance screen

| Deployment | n | Median wall | Range | Sum | Median decode |
| --- | ---: | ---: | ---: | ---: | ---: |
| `nemotron-3.5-lightning:30b-mlx` | 15 | **11.92 s** | 6.48–19.03 s | **186.94 s** | **100.89 tok/s** |
| `gemma4:31b-mlx` | 15 | 41.82 s | 25.50–75.09 s | 637.48 s | 22.77 tok/s |
| `granite4.2:30b` | 15 | 186.09 s | 49.21–654.18 s | 3,380.59 s | 6.35 tok/s* |

These are one-run-per-case screens across naturally different prompts and
answer lengths, not latency distributions. No P90 or P95 is reported.

Granite's asterisk is material. The notebook entered standby during its sweep,
creating a gap of more than eight hours between measured request time and
elapsed sweep time. In several later Granite cases, Ollama also reported
generation durations greater than its own total duration, including 7,079.52
seconds of `eval_duration` inside a 327.71-second request. The raw values are
preserved, but Granite's decode telemetry and exact relative speed are not
trusted. Its observed client wall time remains useful only as diagnostic
evidence that this deployment was impractical in the tested setup.

## Output-level failures in the warm candidates

Gemma passed every hard deterministic output constraint. Nemotron had five
hard failures: four outputs above their word ceiling and one writing output
that exposed technical source labels. Granite had six: four completed outputs
above their ceiling and two length-terminated generations that were also too
long. These are task/output failures, not runtime failures, and remain visible
in the quality report.

## Evaluation handoff

The exact 45 new warm candidates were combined with the selected historical
incumbent responses in evaluation batch
`challenger-evaluation-20260903T074940Z-ae83d012`. It contains seven candidates
for each of the first thirteen cases and eight for each writing case. All 336
bundle artifacts passed hash verification before judgment.

Independent scores were frozen at
`4f2b52a5ad7155d73fe6a2ece17bec012e6b1266f50a1f17172556053015e04a`.
All 83 required within-three-point pairwise comparisons were then frozen at
`3614a407e4c37a81b1eb3526e96608e612bb85e57a3af244104ab90d06a534f0`
before the private model map was opened.
