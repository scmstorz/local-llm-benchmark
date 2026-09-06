# Summarization Track v0.1

Status: frozen development evidence  
Frozen on: 2026-08-28

## Decision scope

This milestone answers a narrow personal question: which tested local Ollama
deployment should be used to produce German briefings of English articles and
research papers when quality, latency and completion reliability all matter?

It is development evidence, not a universal leaderboard. The three cases were
used to establish the harness and rubric, and no untouched holdout set has been
run yet.

## Frozen cases

1. MIT Sloan article on AI and climate goals
2. *TheAgentCompany* main paper
3. METR's *Measuring AI Ability to Complete Long Software Tasks* main paper

The controlled MIT Sloan rerun is used instead of the earlier confounded
performance screen. Every comparison used the same four deployments,
temperature zero, seed 42 and one explicit cold plus one immediate warm run per
model. The two research-paper cases required a 16,384-token context window.

## Development results

| Deployment | MIT Sloan | TheAgentCompany | METR | Mean quality | Mean warm wall | Invalid |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| `muse-glimmer:30b-mlx` | 90.5 | 90 | 94.5 | 91.7 | 60.67 s | 0/3 |
| `qwen3.8:27b-mlx` | 88.5 | 88 | 71 | 82.5 | 53.73 s | 0/3 |
| `qwen3.6:35b-a3b-mxfp8` | 88.5 | 72 | 69 | 76.5 | 18.42 s | 0/3 |
| `gpt-oss:20b` | 82 | 86 | 0 | 56.0 | 37.28 s | 1/3 |

Arithmetic means are descriptive only. Rubric points should not be treated as
a universal interval scale, and a completed-only mean must never hide invalid
runs.

## Provisional deployment roles

### Quality mode: Muse Glimmer

Use `muse-glimmer:30b-mlx` when the cost of missing or distorting a method,
qualification or causal distinction is higher than the latency cost. It is the
only deployment rated excellent on every development case and was strongest on
the most statistically demanding source.

### Fast mode: Qwen 3.6

Use `qwen3.6:35b-a3b-mxfp8` for rapid screening when moderate quality loss is
acceptable. Its mean warm wall time was less than one third of Glimmer's. Both
research-paper cases exposed method-comprehension losses, so important outputs
should be verified or regenerated in quality mode.

### Secondary option: Qwen 3.8

`qwen3.8:27b-mlx` achieved higher mean quality than Qwen 3.6 but ran much closer
to Glimmer in latency. It remains on the descriptive Pareto frontier, yet the
current evidence does not establish a compelling default role between the fast
and quality endpoints.

### Reliability watch: GPT-OSS

`gpt-oss:20b` averaged 84 points on the two cases it completed, then failed the
METR workflow by spending its generation budget in a repetitive hidden-reasoning
loop. Treat completion rate as part of quality. Do not select this deployment
for unattended summarization until broader evidence or a separately reported
configuration change resolves that failure mode.

## Methodology lessons frozen with v0.1

- Deployment configuration, prompt, context and harness are part of the result.
- Warm latency and decode throughput answer different performance questions.
- Temperature zero and a fixed seed improve repeatability but do not guarantee
  byte-identical output.
- Deterministic checks catch truncation and contract failures, not semantic
  quality.
- Source-grounded scoring must distinguish omission, contradiction, certainty
  inflation and invalid completion.
- Completion reliability must be reported alongside quality conditional on
  completion.
- Candidate-to-model mapping must remain hidden until individual and pairwise
  judgments are frozen.

## Known limitations

- Only three development cases have been evaluated.
- All requested outputs were German summaries of English sources.
- Quality was judged once per comparison batch by an interactive Codex session.
- The candidate artifacts were anonymized, but the three completed comparisons
  exposed model mappings in runner output before judgment. The runner was fixed
  after this milestone; future comparisons can achieve cognitive blinding.
- Memory and energy use are not yet measured.

## Exit decision

The track is sufficiently mature to guide current personal model selection.
The next benchmark work should test a different capability rather than add a
fourth similar summarization source. General knowledge and explanation is the
next development track. Untouched summarization holdouts remain necessary
before publication-grade claims.
