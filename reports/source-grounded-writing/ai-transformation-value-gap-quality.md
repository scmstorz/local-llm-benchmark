# AI transformation value gap — quality report

## Result

Five warm candidates were judged together against the frozen source packet,
three user thoughts and 100-point rubric. All independent results were hashed
before the one required pairwise check; the final blind record was frozen at
SHA-256 `a53da0038633115589f31c7523b1a2a076938aed8e876af87bf88a00370dda81`
before the private model mapping was opened.

| Rank | Deployment | Quality | Raw | Warm wall | Cold wall | Words | Outcome |
| ---: | --- | ---: | ---: | ---: | ---: | ---: | --- |
| 1 | `muse-glimmer:30b-mlx` | 88 | 88 | 43.20 s | 62.88 s | 448 | Good |
| 2 | `ornith-1.5:35b` | 82 | 82 | 8.41 s | 21.63 s | 424 | Good |
| 3 | `qwen3.6:35b-a3b-mxfp8` | 79 | 84.5 | 10.85 s | 35.84 s | 485 | Good, label cap |
| 4 | `qwen3.8:27b-mlx` | 69 | 69 | 15.80 s | 38.19 s | 387 | Usable |
| 5 | `gpt-oss:20b` | 0 | 0 | 36.06 s | 41.01 s | 0 | Invalid |

The structural-heading flag is inapplicable to this case: the frozen LinkedIn
task requires short paragraphs but no heading. Raw flags remain unchanged, and
the aggregate reporter now supports case-declared inapplicable compliance
checks instead of treating one task format as universal.

## Score construction

| Deployment | Evidence /25 | User thoughts /15 | Judged dimensions /60 | Cap | Final |
| --- | ---: | ---: | ---: | --- | ---: |
| `muse-glimmer:30b-mlx` | 18 | 15 | 55 | — | 88 |
| `ornith-1.5:35b` | 17 | 15 | 50 | — | 82 |
| `qwen3.6:35b-a3b-mxfp8` | 16.5 | 15 | 53 | technical labels: 79 | 79 |
| `qwen3.8:27b-mlx` | 11 | 15 | 43 | — | 69 |
| `gpt-oss:20b` | 0 | 0 | 0 | empty output: 0 | 0 |

Every complete candidate integrated all three user thoughts substantively.
The task discriminated mainly through source coverage, epistemic calibration,
output hygiene and the ability to relate individual, task, team and enterprise
evidence without collapsing them.

## Candidate findings

### Muse Glimmer

Glimmer produced the strongest cross-source argument. It used concrete support,
consulting, P&G, Copilot and organization-survey evidence while making the
micro-to-enterprise level change explicit. Its main omissions were the
support-study knowledge-transfer limits, P&G secondary findings and the
Copilot task-restructuring result. Calling email-free work blocks
`arbeitsfreie Blöcke` was a small unsupported shift. The output remained the
clearest and most reader-useful complete post.

### Ornith

Ornith delivered the strongest valid speed-quality trade-off. Its post was
concise and coherent, with particularly good P&G, frontier and Copilot
contrasts. It underused the customer-support effect sizes and McKinsey's
workflow-association methodology. It also generalized its opening beyond the
sources, mixed the Copilot assignment and user estimates, and later broadened
the one outside-frontier task. These were meaningful but noncritical losses.

### Qwen 3.6

Qwen 3.6 had the second-highest uncapped content score at 84.5. It covered more
source detail and limitations than Ornith, but printed the internal `[Sxx]` and
`[Txx]` labels throughout the finished post. The predeclared hard constraint
capped the result at 79. The required randomized pairwise check retained
Ornith's lead because the Qwen draft was not publication-ready without repair.

### Qwen 3.8

Qwen 3.8 built a coherent thesis and integrated all user thoughts, but it
omitted the P&G comparison and much of the strongest quantitative support. It
incorrectly claimed that saved Copilot time flowed into longer breaks, treated
suggestive knowledge transfer too definitively and generalized the one
outside-frontier task. At 387 words it also missed the 400–550 target range.

### GPT-OSS

GPT-OSS generated 2,600 hidden tokens in both cold and warm requests, reached
the limit and exposed no visible post. Both visible responses were byte-
identical and empty. This is a reproducible two-run failure signature under the
current settings, not an estimated general failure rate.

## Decision view

The final quality-latency Pareto frontier contains only Ornith and Glimmer:

- **Ornith**: 82 points in 8.41 seconds; best practical default for this task.
- **Glimmer**: 88 points in 43.20 seconds; best when the additional quality is
  worth roughly five times the observed warm latency.

Ornith reached 93 percent of Glimmer's score in about 19 percent of its warm
time. Qwen 3.6 would have remained an interesting content-quality point without
the label leak, but the benchmark evaluates the delivered artifact rather than
a manually repaired draft. Qwen 3.8 and GPT-OSS are dominated on the observed
final quality-latency plane.

No adaptive timing repetitions are required for the Capability Sweep because
the practical ordering is not close. Warm timings are immediate same-prompt
repetitions and may benefit from retained prompt state; they are steady-state
screens, not one-off new-document latency distributions.

## Blinding limitation

The explicit map remained closed through all five independent judgments, their
hash freeze and the pairwise check. The judge had already seen anonymized word
counts and knew recurring deployment behavior from earlier cases, so the empty
GPT-OSS candidate may have been inferable. The evaluation is procedurally
blinded but not guaranteed to be cognitively blind.
