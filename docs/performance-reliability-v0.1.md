# Performance and Reliability Study v0.1

This study measures steady-state behavior as distributions rather than reducing
a deployment to one typical latency. It is intentionally separate from quality
evaluation.

## Decision question

How do `qwen3.8:27b-mlx` and `ornith-1.5:35b` differ in steady-state latency,
throughput, observed technical reliability and deterministic output-contract
reliability on one natural and one controlled workload?

These deployments are decision-relevant defaults from prior capability work:
Qwen 3.8 for difficult knowledge and agentic tasks, and Ornith for
source-grounded text production. The study does not assume that either is a
universal winner.

## Two workload types

The study never pools the two workloads into one latency distribution.

The **natural-output workload** reuses the frozen ML evaluation-leakage task.
It measures experienced time for a realistic German explanation. Answer length
is allowed to vary, so wall time is not interpreted as pure runtime speed. A
deterministic contract checks completion, non-empty German output, word limit,
headings, absence of source labels and absence of reasoning markup. It does not
verify semantic quality.

The **controlled-decode workload** uses identical prompt bytes and a fixed
public input payload. It asks the deployment to emit only `vector` until Ollama
enforces a 256-token limit. A valid observation must end with `done_reason =
length`, report exactly 256 evaluated output tokens and match the output
protocol. Actual prompt-token counts remain visible because tokenizer behavior
can differ across deployments.

## Repetitions and order

Each of the four deployment-workload conditions receives 20 measured runs.
Rather than execute 20 adjacent runs per condition, each condition is divided
into four segments of five. A 16-block Williams-style order distributes the
conditions across block positions and time.

Every block has this lifecycle:

1. require a clean resource gate and empty Ollama state;
2. verify Ollama 0.33.2 and the exact model digest;
3. time an explicit model preload;
4. execute one excluded warm-up;
5. execute at most five measured requests, checkpointing after each;
6. unload the model.

This produces 80 measured requests and 16 excluded warm-ups. A guard before
every measured request checks for blocking processes, runtime drift, digest
drift and unexpected Ollama activity. A pause never consumes a pending sample.

## Failure and interruption policy

Every planned attempt remains visible. Technical completion and output-contract
success are distinct fields. Infrastructure failures are classified as timeout,
runtime unavailable, runtime crash, out of memory, model-load failure, cleanup
failure or other. Completed but malformed, short or contract-breaking outputs
are task/output failures instead of infrastructure failures.

There are no automatic retries after a terminal measured outcome. If the
controller or host disappears before a terminal outcome, resume first searches
for an already completed matching raw run. Only if none exists may that
nonterminal attempt be replaced. Each resumed block receives a new excluded
warm-up.

## Reporting

For each condition, the public aggregate retains all safe numeric raw values
and reports `n`, mean, sample standard deviation, minimum, median/P50, maximum
and nearest-rank P90 when at least 20 valid observations remain. P95 requires at
least 50 observations and P99 at least 100, so neither is permitted in v0.1.

Performance distributions include only technically complete measured runs that
pass their workload-specific deterministic output contract. Reliability counts
all planned attempts. Model load and warm-up measurements remain separate.

The first-content metric is client wall time to the first non-empty assistant
content chunk, not token-level TTFT. No quality score, precise population
failure probability, cost per verified success or composite score is produced.

## Reproducible commands

Preparation creates a checkpoint without contacting Ollama:

```bash
python3 -m local_llm_benchmark.performance_reliability start \
  --plan tasks/studies/performance-reliability-v0.1.json
```

Each authorized live advance executes the next five-run block:

```bash
python3 -m local_llm_benchmark.performance_reliability advance \
  --study-dir results/performance-reliability/studies/STUDY-ID \
  --execute-live
```

Status inspection is offline:

```bash
python3 -m local_llm_benchmark.performance_reliability status \
  --study-dir results/performance-reliability/studies/STUDY-ID
```

The machine-readable frozen contract is
[`performance-reliability-v0.1.json`](../tasks/studies/performance-reliability-v0.1.json).

## Completed execution

The frozen study completed all 80 measured requests and 16 excluded warm-ups.
Both deployments achieved 40/40 technical completions and 40/40 deterministic
output-contract passes across the two workloads. Ornith was faster in the
controlled comparison: median wall time was 2.83 seconds versus 3.63 seconds,
and median decode throughput was 92.21 versus 71.75 tokens per second.

The generated [aggregate](../reports/performance-reliability/performance-reliability-v0.1.md)
contains the public-safe raw numeric values and descriptive distributions. The
curated [interpretation](../reports/performance-reliability/performance-reliability-v0.1-analysis.md)
records the bounded conclusions and an important execution limitation: four
Qwen natural-output observations crossed notebook standby. They remain in the
primary result, while a separately labeled sensitivity view shows that the
median conclusion is stable and the official P90 is not.
