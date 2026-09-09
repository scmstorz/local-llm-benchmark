# German text quality stochasticity study v0.1

## Result

The first repeated-quality study produces a task-specific routing result rather
than one universal winner:

- `muse-glimmer:30b-mlx` won all five blinded pairs on the METR research-paper
  summary and averaged 96.6/100, versus Ornith's 93/100.
- `ornith-1.5:35b` won all five blinded pairs on the source-grounded LinkedIn
  post and scored 88.5/100 in every run, versus Glimmer's 69.3 mean and 59
  median.
- Ornith returned byte-identical output across all five repetitions of each
  case. Every Glimmer response was byte-distinct despite temperature zero and
  a fixed seed.
- All 20 requests completed and passed the deterministic output checks. The
  observed quality problem was semantic, not a transport or format failure.

The operational default remains Ornith for source-grounded public writing.
Glimmer is the better quality-first choice for this dense research-paper
summary when its longer wait is acceptable.

## Quality distributions

Scores use each case's frozen source-grounded 0-100 rubric. Standard deviation
is the sample standard deviation. At `n = 5`, raw values, center and range are
reported; no tail percentiles or precise failure probabilities are claimed.

| Case | Deployment | Raw scores | Mean | Median | SD | Range | Pairwise |
| --- | --- | --- | ---: | ---: | ---: | --- | --- |
| METR summary | `muse-glimmer:30b-mlx` | 96, 97, 97, 98, 95 | 96.6 | 97 | 1.14 | 95-98 | 5 wins, 0 losses |
| METR summary | `ornith-1.5:35b` | 93, 93, 93, 93, 93 | 93.0 | 93 | 0.00 | 93-93 | 0 wins, 5 losses |
| Source-grounded post | `ornith-1.5:35b` | 88.5, 88.5, 88.5, 88.5, 88.5 | 88.5 | 88.5 | 0.00 | 88.5-88.5 | 5 wins, 0 losses |
| Source-grounded post | `muse-glimmer:30b-mlx` | 87, 59, 82.5, 59, 59 | 69.3 | 59 | 14.19 | 59-87 | 0 wins, 5 losses |

The pairwise judgments were predeclared same-repetition comparisons in a
randomized A/B orientation. They were recorded only after all scalar scores
had been frozen and did not change those scores.

## Descriptive performance

Each measured request followed an empty-state resource gate and a separate
model preload. Values below describe the warm measured requests, not model-load
time. Natural response lengths differ, so throughput and wall time are kept
separate from quality.

| Case | Deployment | n | Mean wall | Median | SD | Range | Mean decode |
| --- | --- | ---: | ---: | ---: | ---: | --- | ---: |
| METR summary | `muse-glimmer:30b-mlx` | 5 | 84.54 s | 84.00 s | 8.78 s | 74.03-96.82 s | 27.87 tok/s |
| METR summary | `ornith-1.5:35b` | 5 | 38.59 s | 37.77 s | 3.72 s | 34.45-44.17 s | 73.54 tok/s |
| Source-grounded post | `muse-glimmer:30b-mlx` | 5 | 67.20 s | 69.80 s | 15.02 s | 52.05-89.42 s | 29.30 tok/s |
| Source-grounded post | `ornith-1.5:35b` | 5 | 21.44 s | 20.14 s | 3.38 s | 18.05-26.87 s | 69.82 tok/s |

Measured request time totaled 1,058.85 seconds. Glimmer's mean wait was 2.19
times Ornith's on the summary and 3.13 times Ornith's on the writing case.

## What varied

### Research-paper summary

Both deployments were excellent. Ornith produced one long, highly faithful
963-word summary in every repetition. Glimmer produced five distinct summaries
between 646 and 734 words. Its variants more consistently retained the
bootstrap interval, repeated-run design and methodological uncertainty while
compressing the source more aggressively. The result is a small but repeatable
quality premium for Glimmer, confirmed in every same-repetition pair.

### Source-grounded public writing

Ornith produced the same compact, historically scoped 426-word post five times.
It omitted some retry economics, trajectory detail and DORA qualifications but
did not make a material factual error.

Glimmer's five distinct posts ranged from good to poor. Three runs described
the best systems in the historical SWE-Lancer evaluation as today's best
models; two of those also inflated the 26.2-percent individual-task result to
roughly one third. This is the exact consequential error category that made the
case decision-relevant. A fourth Glimmer run retained the historical boundary
but stated fallback cost-saving potential without the calculation's decisive
verification-time and historical-cost assumptions. Only one Glimmer run was
free of a major or critical error.

The important distinction is therefore not merely that Glimmer varies. Its
variation is beneficial on the summary but unsafe on the public writing task
because a recurring variant changes the evidential scope.

## Method

The frozen design crossed two deployments with two hard existing cases and
five fresh repetitions per cell:

- temperature `0.0`, seed `42`, thinking disabled and `num_predict = 2600`;
- exact prompts, private source inputs, case versions, model digests and Ollama
  `0.33.2` recorded before execution;
- one warm measured request after a separate preload for every unit;
- a two-snapshot competing-process gate and an empty Ollama state before every
  unit;
- no answer-dependent retries and no reuse of historical outputs;
- fresh opaque candidate IDs, scalar judgment freeze, predeclared pairwise
  checks and mapping reveal only after both freezes.

All 20 units completed, and every candidate was non-empty, German, within the
hard word limit, complete and free of leaked reasoning or source-location
labels.

## Integrity and limitations

- Frozen plan commit: `7d09769`
- Controller commit: `1cba52c`
- Study ID: `quality-study-20260908T140753Z-07fb3b80`
- Scalar judgment freeze: `9c9863d41b7f6ac257ffd55d2d1f261432216cfd430793e3bca25020f74768d5`
- Pairwise judgment freeze: `fe893ef1516c5907e172fa3ab16a9ebdd2a8e57645c95b0815617656d988cdf2`

The private mapping remained closed until both judgment files were frozen.
The evaluation was procedurally blinded, but not guaranteed to be cognitively
blind: candidate word counts and deployment-level timing summaries made the
five-identical-response group partly inferable.

This is a two-case, two-deployment study under one deterministic-request
configuration. It does not estimate temperature or seed sensitivity, rare
runtime failures, latency tails or quality on German text work in general. The
interactive judge is version-sensitive; a later direct challenger comparison
must rejudge the complete candidate set.
