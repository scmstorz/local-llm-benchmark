# Agentic software development reality gap — quality report

## Result

Five warm candidates were judged together against the frozen source packet,
three user thoughts and 100-point rubric. All independent results were hashed
before the one required pairwise check; the final blind record was frozen at
SHA-256 `d0d16f4d7464e10bf611221d5b379446062921796e50dbb8a328d957a9a83714`
before the private model mapping was opened.

| Rank | Deployment | Quality | Raw | Warm wall | Cold wall | Words | Outcome |
| ---: | --- | ---: | ---: | ---: | ---: | ---: | --- |
| 1 | `ornith-1.5:35b` | 83 | 83 | 9.05 s | 21.60 s | 415 | Good |
| 2 | `qwen3.8:27b-mlx` | 81 | 81 | 17.82 s | 36.93 s | 466 | Good |
| 3 | `qwen3.6:35b-a3b-mxfp8` | 63.5 | 63.5 | 10.87 s | 64.97 s | 495 | Usable, label leak |
| 4 | `muse-glimmer:30b-mlx` | 59 | 73 | 39.85 s | 69.69 s | 418 | Poor, critical-error cap |
| 5 | `gpt-oss:20b` | 0 | 0 | 29.24 s | 37.34 s | 0 | Invalid |

The structural-heading flag is inapplicable to this case: the frozen LinkedIn
task requires short paragraphs but no heading. Raw flags remain unchanged.

## Score construction

| Deployment | Evidence /25 | User thoughts /15 | Judged dimensions /60 | Cap | Final |
| --- | ---: | ---: | ---: | --- | ---: |
| `ornith-1.5:35b` | 15 | 15 | 53 | — | 83 |
| `qwen3.8:27b-mlx` | 15 | 15 | 51 | — | 81 |
| `qwen3.6:35b-a3b-mxfp8` | 9.5 | 15 | 39 | labels: ceiling 79, nonbinding | 63.5 |
| `muse-glimmer:30b-mlx` | 15 | 15 | 43 | one critical error: 59 | 59 |
| `gpt-oss:20b` | 0 | 0 | 0 | empty output: 0 | 0 |

Every complete candidate integrated all three personal thoughts
substantively. The task discriminated through source selection, historical
scope, harness evidence, reliability interpretation, causal calibration and
output hygiene rather than simple recall of the user brief.

## Candidate findings

### Ornith

Ornith produced the strongest complete post. It was the only candidate to
combine exact historical SWE-Lancer boundaries, direct fixed-model SWE-agent
interface evidence, the 207-day task-horizon trend and the shorter 80-percent
reliability horizon in a compact natural argument. It also integrated all
three user thoughts without presenting them as research. Its main omissions
were retry economics, time-horizon external-validity evidence and most of
DORA's methodology. One DORA mechanism was stated slightly more definitely
than the source supports.

### Qwen 3.8

Qwen 3.8 offered the better DORA conclusion: organizations should form local
hypotheses and experiment rather than buy one tool or trust aggregate
productivity claims. It also reconciled autonomous capability with the
experienced-developer slowdown and integrated the full user position. It lost
evidence points by omitting SWE-agent's direct interface findings and all
reasoning-effort or retry economics. It presented plausible mechanisms for the
developer slowdown too causally and called the early-2025 tools current.

### Qwen 3.6

Qwen 3.6 built a coherent systems argument and covered all three user thoughts,
but its research calibration was materially weaker. It inferred that
95-percent reliability remains far away even though the study says its data
cannot estimate that level. More seriously, it turned DORA's observational
moderation into a causal necessary-condition claim and incorrectly implied
that missing organizational capabilities produce instability instead of the
reported coexistence of throughput and instability. The response also printed
internal S- and T-labels. Its raw score was already below the 79-point label
ceiling, so the compliance cap did not numerically lower the result.

### Muse Glimmer

Glimmer produced a strong, readable synthesis with complete user-thought
integration and good contrasts among autonomous benchmarks, reliability, the
field trial and DORA. Its opening, however, called the strongest historical
SWE-Lancer deployment one of today's best models and rounded the 26.2 percent
individual-task result to roughly one third. The first claim matches the
rubric's critical current-leaderboard error, capping the otherwise 73-point
post at 59.

### GPT-OSS

GPT-OSS generated 2,600 hidden tokens in both cold and warm requests, reached
the limit and exposed no visible post. Both visible responses were byte-
identical and empty. This is a reproducible two-run failure signature under the
current settings, not an estimated general failure rate.

## Pairwise check

Ornith and Qwen 3.8 differed by two points, triggering the only randomized
pairwise comparison. Qwen 3.8 was presented first. It retained an advantage on
DORA's local-experiment implication, but Ornith won because it supplied more
precise historical, interface and reliability evidence in a more compact and
natural post. No score was adjusted.

## Decision view

Ornith is the sole observed quality-latency Pareto deployment: it has both the
highest final quality and the shortest valid warm wall time.

- **Ornith:** 83 points in 9.05 seconds; strongest practical endpoint.
- **Qwen 3.8:** 81 points in 17.82 seconds; close quality, nearly twice the
  observed warm latency.
- **Qwen 3.6:** faster than Qwen 3.8 but materially weaker and noncompliant.
- **Glimmer:** slower and lower-scoring after the critical historical error.
- **GPT-OSS:** fast hidden decoding without a usable outcome.

No adaptive timing repetitions are required for the Capability Sweep because
there is no unresolved quality-latency decision. Warm timings are immediate
same-prompt repetitions and may benefit from retained prompt state; they are
steady-state screens, not latency distributions.

## Response variation

Ornith produced byte-identical cold and warm posts. GPT-OSS produced the same
empty visible response twice. Qwen 3.6, Qwen 3.8 and Glimmer produced different
cold and warm responses despite temperature zero. These pairs are observations,
not a quality-stochasticity estimate.

## Blinding limitation

The explicit map remained closed through all five independent judgments, their
hash freeze and the required pairwise check. Aggregate integrity inspection had
already exposed one empty candidate, and recurring deployment behavior made
its identity plausibly inferable. Candidate prose and the actual map remained
closed until the final blind freeze, so the evaluation is procedurally blinded
but not guaranteed to be cognitively blind.
