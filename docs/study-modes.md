# Benchmark Study Modes

This project deliberately separates several study modes. They answer different
questions, need different repetition counts and must not be collapsed into one
undifferentiated benchmark score.

## Current decision

The broad **Capability Sweep** and two initial **Quality Stochasticity Study**
slices are complete. The first completed study follows the protocol frozen in
[`quality-stochasticity-v0.1.md`](quality-stochasticity-v0.1.md) and repeats two
deployments across two discriminative text cases five times per condition. Its
public-safe result is recorded in
[`text-quality-v0.1.md`](../reports/quality-stochasticity/text-quality-v0.1.md).
The second completed study follows
[`quality-stochasticity-knowledge-v0.2.md`](quality-stochasticity-knowledge-v0.2.md),
with results in its generated
[`aggregate`](../reports/quality-stochasticity/knowledge-quality-v0.2.md) and
curated [`interpretation`](../reports/quality-stochasticity/knowledge-quality-v0.2-analysis.md).
The first **Performance and Reliability Study** is complete. It compares two
decision-relevant deployments on one natural-output workload and one controlled
256-token decode workload. Its 80 measured requests remain separate from the
quality studies; see the generated
[`aggregate`](../reports/performance-reliability/performance-reliability-v0.1.md)
and curated
[`interpretation`](../reports/performance-reliability/performance-reliability-v0.1-analysis.md).

This staging is a compute-budget decision, not a claim that variation and
reliability are unimportant. Running enough repetitions for defensible latency
tails on every model-task combination would make the current capability phase
unnecessarily slow.

A separate **Multi-Model Deliberation Study** is also planned. It will test a
different system hypothesis and must not be mixed into single-model capability
scores.

## 1. Capability Sweep

### Question

How capable is each deployment across a broad set of personally relevant
tasks, and which recurring strengths, weaknesses and failure modes appear?

### Design

- many distinct cases across task classes
- few generations per model and case
- one predeclared quality candidate per model and case
- one cold and one immediate warm run for the initial performance screen
- two additional warm runs only when close or unstable measurements could
  change a case-level decision
- blinded, source-grounded rubric judgment with randomized pairwise checks for
  close scores
- separate reporting of quality, compliance and latency

### Claims it supports

- quality differences across tasks
- cross-task robustness and recurring error patterns
- workflow-level invalid or capped outcomes
- provisional quality-latency trade-offs

### Claims it does not support

- stable P90, P95 or P99 latency estimates
- precise runtime failure probabilities
- the within-task quality distribution of a deployment
- publication-grade tail-latency comparisons

The current Hard Knowledge v0.2 block remains unchanged and belongs to this
mode.

## 2. Quality Stochasticity Study — two initial slices complete

### Question

When the same deployment answers the same task repeatedly, how much does
result quality vary, and how often does it produce a usable result?

This is distinct from the Capability Sweep. Running many tasks once measures
cross-task robustness; running one task many times measures within-task
stochasticity.

### Initial design

- select a small number of representative, discriminative frozen cases
- start with approximately five judged generations per model and case
- use identical prompts, inference settings and evaluation rubrics within each
  repeated condition
- predeclare which generation attempts are quality candidates
- judge outputs blinded and preserve every individual dimension score
- reuse existing cold and warm responses only when they match the frozen
  generation condition; do not silently replace a known weak candidate
- increase repetitions only when the initial study exposes decision-relevant
  variation

### Report

- measured generations `n`
- mean, median, standard deviation, minimum, maximum and raw quality scores
- deterministic compliance rate
- verified task-success and task-failure counts
- rubric-dimension distributions
- recurring factual, reasoning, formatting and calibration errors
- response identity or byte-level repeatability where informative

Five quality samples are exploratory. They can reveal material instability but
cannot establish rare-event rates or precise distribution tails.

The initial text study found task-specific rather than universal superiority.
Glimmer won all five METR-summary pairs, while Ornith won all five
source-grounded-writing pairs. Ornith repeated one byte-identical response per
case; Glimmer produced five variants per case and repeated a consequential
historical-to-current claim error in three of five writing observations. These
are observed counts under one fixed request condition, not estimated failure
probabilities.

### Second completed slice: difficult general knowledge

The second study crosses `qwen3.8:27b-mlx` and
`muse-glimmer:30b-mlx` with the medical-screening Bayes case and the ML
evaluation-leakage case. Glimmer was selected as the strongest exact-case
challenger from an internally comparable prior judgment batch; it led Qwen 3.8
on both cases. Five fresh repetitions per condition produce 20 measured runs
and ten predeclared same-repetition pairwise checks.

All 20 fresh generations completed technically and passed deterministic output
checks. Direct pairwise preferences split 5–5. Qwen's scores remained in the
narrow ranges 90–92.5 and 91.5–93, while Glimmer ranged from 80–94.5 and
85.5–95.5. Glimmer produced the highest individual scores but also two Bayes
answers with a major lead-time contradiction. Qwen therefore supplied the
stronger observed quality floor for these two tasks; this is not a universal
model ranking.

Future repeated-quality studies use the additive
[Evaluation Pipeline v0.2](quality-evaluation-v0.2.md). It validates complete
case-specific judge records, freezes scalar results before predeclared
pairwise comparisons, prevents model and performance metadata access until
both freezes are hashed, and then generates separate public-safe outcome
layers. The completed v0.1 study remains historical evidence and is not
retroactively relabeled as a v0.2 pipeline run.

## 3. Performance and Reliability Study — v0.1 complete

### Question

How fast is a deployment normally, how bad can its observed tail become, and
how often does an attempt fail technically or produce an unusable task result?

### Two workload types

Performance must be measured with two explicitly different workload types:

1. **Real-workload latency** allows the natural response length and measures
   experienced end-to-end waiting time.
2. **Controlled runtime performance** fixes or tightly controls input and
   output token counts to isolate prefill and decode behavior.

End-to-end latency from naturally different response lengths must not be
presented as pure runtime speed. Output-token count and throughput remain
visible beside wall time.

### Initial design

- use one or a few representative workloads rather than every capability case
- record model load and cold start separately
- discard declared warm-up runs from the steady-state distribution
- start with at least 20 measured warm runs per selected configuration when
  P90 is a decision-relevant exploratory statistic
- consider 50 measured runs for P95 and at least 100 for exploratory P99
- preserve the exact sample count and every individual attempt
- keep system-idle checks and unrelated Ollama activity monitoring
- never pool unlike tasks into one runtime distribution without labeling the
  workload mixture explicitly

The frozen v0.1 implementation applies this design to Qwen 3.8 and Ornith. Each
of the four conditions receives 20 measured observations, divided into four
five-run blocks to reduce time- and order-confounding. Every block begins with
an empty-state gate, model preload and one excluded warm-up. See the
[v0.1 protocol](performance-reliability-v0.1.md).

All 80 measured requests completed technically and passed their deterministic
output contracts. Ornith had the lower median wall time and higher median
decode throughput in the controlled 256-token workload. Four Qwen natural
observations crossed notebook standby; they remain in the primary distribution,
and the interpretation reports a separate sensitivity view. This preserves the
predeclared sample while preventing the affected P90 from being mistaken for
an intrinsic deployment tail.

Percentile thresholds are pragmatic, not guarantees of precision:

| Measured runs | Permitted interpretation |
| ---: | --- |
| fewer than 10 | Raw values, median and range; no tail claim |
| at least 20 | Exploratory P90 |
| at least 50 | P95 becomes more informative |
| at least 100 | Exploratory P99 |

When practical, uncertainty intervals or order-statistic sensitivity should
accompany tail estimates. A percentile label must never imply more precision
than its sample size supports.

### Performance report

For each metric supported by the harness, retain and summarize:

- measured runs `n`
- mean and standard deviation
- minimum and maximum
- median or P50
- P90, P95 or P99 only when the sample size and report language permit it
- every raw value

Candidate metrics include:

- end-to-end latency
- true time to first token when measured by the streaming client
- model-load duration
- prompt or prefill duration and throughput
- generation duration and output tokens per second
- memory usage when repeated measurement is reliable
- for agentic studies: task duration, steps, tool calls, retries, tokens and
  time to verified success

## Failure and outcome model

Failures must remain in the dataset. Performance among successful runs and
the probability of success are separate results.

At minimum, store two status dimensions:

```text
execution_status:
  completed
  infrastructure_failed

task_status:
  passed
  failed
  unscored
```

An infrastructure or runtime failure means that execution could not complete
normally. A task failure means that execution completed but the result did not
meet predeclared success or validity criteria.

Failure codes may include:

```text
timeout
runtime_crash
out_of_memory
model_load_failure
malformed_output
empty_output
tool_failure
agent_max_steps_exceeded
verification_failed
other
```

Some codes require context. For example, malformed output is normally a task
failure after technically successful generation, while a tool failure may be
infrastructure-related or part of the agent's task trajectory. The two status
dimensions, failure stage and stored error detail must preserve that
distinction.

Reliability reporting includes:

- total attempts
- successful and failed execution counts
- infrastructure failure rate
- verified task-success and task-failure counts
- task failure rate
- failure-code taxonomy and individual failed attempts

Failed attempts must not disappear from latency accounting. Conditional
latency among successful runs should be reported alongside reliability, while
failure durations remain available separately.

## 4. Multi-Model Deliberation Study — later

### Question

Can two complementary local deployments produce a better verified result than
either deployment alone when inference time is not a binding constraint?

The initial pairing of interest is `qwen3.8:27b-mlx` with
`muse-glimmer:30b-mlx`. This is a harness or system-capability experiment, not
evidence about either model in isolation.

### Initial protocol

1. Each deployment produces an independent answer from the original task and
   source context. Neither sees the other answer during this stage.
2. Each deployment receives the other answer under an opaque label and writes
   a structured critique against the frozen task rubric or a predeclared
   failure-boundary checklist.
3. A predeclared deployment produces a final synthesis from the original task,
   both drafts and both critiques. A symmetric alternative may let both revise
   and then use blinded evaluation to select the stronger revision.
4. The final outputs are judged with the same deterministic checks, grounded
   rubric and pairwise policy as the single-model baselines.

Independent drafts reduce anchoring. Structured critique is preferred over an
open-ended debate, which can amplify verbosity, deference or a persuasive
mistake. Shared misconceptions remain a known limit: two models cannot reliably
correct a fact neither model knows, so reference-grounded evaluation or a
deterministic verifier remains essential.

### Resource protocol

Run the two deployments sequentially through one Ollama server. Explicitly
unload one model before loading the other, persist the complete stage
trajectory and accept the additional model-load time. Concurrent execution or
two Ollama instances are not required and may exceed unified-memory capacity.

Record at least:

- participating deployments and their fixed roles
- stage prompts and prompt versions
- independent drafts, critiques and final synthesis
- model-load and inference duration for every stage
- input and output tokens per stage
- total time and compute time per verified final outcome
- whether the synthesis repairs, preserves or introduces each material error

Compare at minimum `Qwen alone`, `Glimmer alone`, `Qwen -> Glimmer critique ->
Qwen revision` and the full independent-draft/cross-critique/synthesis
protocol. Do not assume deliberation is beneficial; measure quality gain,
regressions and added compute separately.

## Reporting and model selection

The four logical distributions are:

1. **Performance:** How long does a successful run take?
2. **Reliability:** How often does execution complete and yield a usable
   result?
3. **Quality:** How good is the result, and how much does it vary?
4. **Trajectory:** For agentic tasks, how much work is required to succeed?

A rubric total for one response remains useful. A universal model score that
silently mixes quality, speed and reliability does not. Primary reports should
use separate metrics, constraint filters and Pareto views.

An optional operational metric is compute time per verified successful result:

```text
sum(duration of all attempts) / number of verified successful outcomes
```

It includes the cost of failed attempts but supplements rather than replaces
the underlying distributions and failure counts. Longer-term model selection
optimizes a combination of time, reliability, quality and resource cost per
verified successful outcome, with weights determined by the actual workflow.

Useful distribution views include raw-value tables, empirical cumulative
distribution functions, box plots and histograms. Visualizations are added
only when the sample size makes them informative.
