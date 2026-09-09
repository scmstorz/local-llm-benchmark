# General-Knowledge Quality Stochasticity Study v0.2

This document records the frozen plan for the second repeated-quality study.
The machine-readable contract is
[`quality-stochasticity-knowledge-v0.2.json`](../tasks/studies/quality-stochasticity-knowledge-v0.2.json).
No inference was performed while selecting, authoring, validating or
checkpointing this study.

## Decision question

Are `qwen3.8:27b-mlx` and its strongest exact-case challenger stable on
difficult German knowledge and transfer work, and does either deployment show
a repeatable quality advantage?

This is a within-task quality study, not another broad capability sweep. It is
designed to replace two isolated observations with small exploratory
distributions while keeping compute bounded.

## Why these deployments

`muse-glimmer:30b-mlx` was selected from existing evidence rather than from an
overall leaderboard. In the internally comparable five-way late-challenger
judgment, it led Qwen 3.8 on both selected cases:

| Case | Qwen 3.8 | Glimmer | Observed gap |
| --- | ---: | ---: | ---: |
| Medical screening and Bayes | 88.5 | 94.0 | Glimmer +5.5 |
| ML evaluation leakage | 89.5 | 93.5 | Glimmer +4.0 |

Ornith and Gemma were considered. Glimmer is the stronger challenger for this
specific two-case question because it led both exact cases in the comparable
prior evidence. These historical scores only select the boundary; none is
reused as a study observation.

## Why these cases

The cases represent complementary forms of difficult knowledge work:

- **Medical screening and Bayes** requires a correct quantitative result,
  natural-frequency explanation, base-rate calibration and separation of test
  accuracy from actual screening benefit.
- **ML evaluation leakage** requires conceptual transfer from a flawed
  experiment to a deployment-aligned evaluation design, including leakage,
  selection bias and nested cross-validation.

Both cases are already frozen, source-backed for the judge and meaningful for
the user's real need: reliable, well-explained answers rather than trivia.

## Frozen design

The full product is two deployments by two cases by five fresh measured
generations: **20 runs**. Settings remain fixed at temperature 0, seed 42,
thinking disabled, 8,192 context tokens and a 2,600-token generation limit.
Each unit starts only after the existing resource gate reports an empty Ollama
state and no known competing workload. The selected model is preloaded, the
preload is timed separately, one warm generation is recorded and the model is
unloaded after the unit.

Execution order is balanced before execution. Every condition appears five
times; no answer-dependent retries are allowed. Runtime failures remain
results. At `n=5`, quality scores, raw timing, median, range and observed
failure counts are descriptive. P90, P95, P99 and precise failure-rate claims
are forbidden.

## Evaluation workflow

After all 20 terminal units, the controller creates one blinded ten-candidate
bundle per case and five predeclared same-repetition pairs per case. Evaluation
uses Pipeline v0.2:

1. initialize the evaluation state;
2. submit and freeze all 20 schema-valid scalar judgments;
3. submit and freeze the ten pairwise decisions without changing scores;
4. reveal model identities and performance data only after both hashes exist;
5. generate the sanitized JSON aggregate and Markdown report.

The report keeps quality, variation, recurring errors, pairwise preference,
technical completion and descriptive performance separate. It produces no
universal composite score.

## Prepared checkpoint

Preparation may create a checkpointed study directory with all 20 units still
`pending`. The `start` operation performs no inference and does not contact
Ollama. The first live unit still requires a later explicit user go-ahead and
the full resource gate. In particular, Mnemosyn, News App, Blog Read-o-Matic
and competing test runners must not be active.

Once live execution is allowed, exactly one unit is attempted per command:

```bash
python3 -m local_llm_benchmark.quality_stochasticity advance \
  --study-dir results/quality-stochasticity/studies/STUDY-ID \
  --execute-live
```

This one-unit boundary makes interruptions and notebook standby recoverable.
It is not a manual quality-selection boundary: the next unit is fixed by the
frozen plan.

## Execution outcome

The later authorized live phase completed all 20 planned units. All were
technical successes, passed deterministic output checks and produced usable
answers. Evaluation Pipeline v0.2 froze all scalar judgments and predeclared
pairwise decisions before reveal. The generated public-safe
[`aggregate`](../reports/quality-stochasticity/knowledge-quality-v0.2.md) and
curated [`interpretation`](../reports/quality-stochasticity/knowledge-quality-v0.2-analysis.md)
record the results and their small-sample limits.
