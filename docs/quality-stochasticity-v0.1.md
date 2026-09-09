# Quality Stochasticity Study v0.1

## Decision question

Is the provisional choice of Ornith as the default local deployment for
single-turn German text work stable across repeated generations, and when does
Glimmer provide a repeatable quality advantage worth its longer observed wait?

This study measures within-condition quality variation. It is not another broad
Capability Sweep and not a latency-tail or rare-failure study.

## Frozen initial slice

The initial design crosses two deployments with two existing hard cases:

- `ornith-1.5:35b` and `muse-glimmer:30b-mlx`;
- the METR long-software-task paper summary; and
- the source-grounded agentic-software-development LinkedIn post.

The summary case is an intentionally close comparison: both deployments were
excellent in the prior joint judgment, with Glimmer ahead by three points. The
writing case is an intentionally decision-relevant disagreement: Ornith led by
24 points after Glimmer made a critical historical/current-leader claim. The
combination tests both rank stability near a decision boundary and recurrence
of a consequential error mode.

## Repetitions and generation condition

Every deployment-case condition receives five fresh measured generations, for
20 quality candidates in total. Historical cold or warm outputs are not reused.
Every sample uses the same frozen prompt and input, temperature zero, seed 42,
thinking disabled, and the case-specific context window. Fixing the seed is
intentional: the target is operational repeatability under the project's normal
deterministic-request configuration, not sensitivity to sampling temperature or
random seed.

Before every measured request, the controller requires an empty Ollama state,
checks runtime and model digest, observes known competing processes twice, and
preloads only the selected model. The selected model is unloaded after the
sample. Model-load time is recorded separately and the measured request is
labelled warm. Timing remains descriptive because five samples cannot support
tail-percentile claims.

The execution order is frozen as a balanced 20-unit sequence before inference.
Every terminal attempt remains in the study. Runtime failures, empty or
malformed output, length termination, and deterministic compliance failures are
not silently removed or retried. If the controller or host disappears before a
terminal Ollama response exists, the partial attempt is preserved and one
replacement may be started; this is a control-plane recovery, not an
answer-dependent retry.

## Blinded evaluation

After all units are terminal, the controller creates one ten-candidate bundle
per case with fresh opaque IDs. The private mapping remains outside the judge
bundle. The interactive judge first scores every candidate independently using
the existing source-grounded 0–100 rubric and freezes those judgments.

Five same-repetition cross-deployment pairs per case are then judged in their
predeclared randomized orientation. Pairwise review records a preference or tie
but never changes the independent scalar scores. The mapping is opened only
after both scalar and pairwise records are frozen.

## Reporting boundary

For each deployment-case condition, report all five raw scores, mean, median,
standard deviation, minimum, maximum, deterministic compliance, usable-output
count, byte-identical response groups, and recurring error categories. Report
pairwise wins, losses and ties separately.

Do not report P90, P95, P99, a precise failure probability, or a universal
composite score. Cross-case aggregation is secondary to the two case-level
distributions. Any operational recommendation must distinguish observed
quality, consistency, runtime completion and descriptive waiting time.
