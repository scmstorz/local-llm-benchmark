# Benchmark Design

## 1. Goals and non-goals

The benchmark lab is optimized for personal model-selection decisions on one
fixed local system. It is neither a universal hardware leaderboard nor an
attempt to rebuild Pipette.

Guiding question:

> Which local Ollama configuration delivers the best verified outcome for my
> actual tasks at acceptable latency and resource usage?

Non-goals for the first version:

- laboratory-grade temperature or energy measurements
- comparisons across several runtimes or devices
- broad coverage of public benchmark suites
- publication-grade agent-loop and tool comparison in the initial Track A slice
- one composite ranking number that hides all trade-offs

The long-term coding and agentic direction is capability-aware model selection:
find a least-cost deployment configuration that meets a task-specific verified
success requirement, then compare routing policies only after enough evidence
exists. This is a future track, not a reason to expand the current Capability
Sweep. See [`coding-routing-roadmap.md`](coding-routing-roadmap.md).

## 2. Experimental units

### Deployment configuration

Record at least:

```text
model_name
model_digest
model_family
parameter_size
quantization
ollama_version
ollama_options
context_window
temperature
seed
thinking_mode
hardware
memory_total
os_version
```

An Ollama model name alone is insufficient because tags can change. The digest
of the artifact that actually ran must therefore be part of the identity.

New deployments are a normal operating condition. The task-suite manifest is
therefore independent of the tracked model catalog. `model-register` records
tag, full digest, selected public metadata and Ollama version without inference;
the same tag with a new digest is appended. A dated cohort can then bind any
number of cataloged deployments to an unchanged suite. Completed newcomer
sweeps may be assembled into one blinded batch with dynamic per-case candidate
counts, so adding a model requires new evidence but no runner code.

Suite execution checkpoints after the cold request and after every terminal
case. A resume operation may continue only missing or nonterminal cases. It
must retain partial attempts, restart an interrupted case as a fresh cold/warm
pair, leave explicit failures untouched and reject drift in suite hash,
methodology, model digest or Ollama runtime. This supports long local runs
without turning an observed failure into a silent retry.

### Benchmark configuration

```text
suite_version
task_id
task_version
prompt_id
prompt_version
harness_git_commit
evaluator_version
run_id
started_at
```

### Result

Do not combine quality and performance into a score prematurely:

```text
quality:
  deterministic_score
  rubric_dimensions
  judge_score
  human_score

performance:
  wall_time_seconds
  load_duration_seconds
  prompt_eval_count
  prompt_eval_duration_seconds
  eval_count
  eval_duration_seconds
  prompt_tokens_per_second
  output_tokens_per_second
  peak_memory_bytes

execution:
  status
  error
  retries
  termination_reason
```

Record TTFT only when the client measures the interval to the first streamed
token. Name prefill time derived from Ollama's aggregate final values
accordingly; do not present it as true TTFT.

## 3. Task design for the first version

### Extraction

Extraction is a useful later task class because its expected result can be
defined as a schema and evaluated using precision, recall, F1 and schema
validity. It can also calibrate the harness with largely deterministic results.

### Reasoning

Reasoning tasks need a machine-verifiable final answer. Free-form explanations
are assessed separately; explanation length alone is not a quality signal.

### Summarization

Each case defines atomic, source-grounded key facts and a rubric covering:

- coverage of important claims
- factual accuracy and freedom from contradictions
- prioritization
- clarity
- compression

"Relevant information per word" is interesting but not a standalone ground-
truth score. A Pareto view of coverage/factuality versus output length is more
useful because it does not reward brevity that omits essential information.

All three summarization cases are explicitly cross-lingual: an English article
or research paper is summarized in German. This is a task property, not the
language of the application or its documentation. The two research-paper cases
also demonstrate that each case may declare a minimum safe context window which
the runner enforces before inference.

### General knowledge and explanation

General-knowledge candidates answer from internal knowledge without browsing
or supplied sources. Evaluation nevertheless needs a frozen factual authority.
Each case therefore contains a project-authored reference dossier based on
authoritative sources and declares `source_delivery: judge_only`. The runner
verifies and packages that dossier for the interactive judge but does not
inject it into the candidate prompt.

The rubric separates factual coverage from explanatory quality and epistemic
precision. This prevents a merely correct list of facts from receiving the
same result as an answer that makes the mechanism understandable, while also
preventing elegant prose from hiding a central misconception.

### Source-grounded professional writing

This track evaluates transformation of supplied evidence into an original
professional artifact. It is distinct from both summarization and online
research: the candidate neither condenses one coherent source nor discovers
and selects publications itself.

Each case provides at least two separately versioned candidate inputs:

1. a project-authored evidence packet whose sections visibly retain their
   source boundaries; and
2. a user brief containing the required personal ideas or perspective.

The evidence packet should contain atomic source-specific notes about methods,
findings and limitations. It must not contain transitions, an overall thesis,
a recommended evidence order or a ready-made conclusion. Otherwise the packet
would silently perform the cross-source reasoning the benchmark is intended to
measure. Each visible input is hashed independently, substituted through its
own prompt placeholder and retained separately in the judge bundle.

Evaluation separates source coverage, faithful integration of user ideas,
factual and epistemic accuracy, cross-source synthesis, audience value, style
and compression. Personal thoughts may shape the argument but must not be
misrepresented as empirical findings. The first development case targets a
German LinkedIn post based on five English-language source cards and exactly
three user-authored thoughts.

### Non-coding agentic work

The next breadth expansion is not another article task. It is an
`Agentic Log Incident Analysis` family: a read-only, offline, multi-file
incident investigation with stable evidence citations and a deterministically
checkable structured report. Its design and the explicitly deferred spreadsheet,
Word and PDF/OCR sequence are recorded in
[`non-coding-agentic-roadmap.md`](non-coding-agentic-roadmap.md).

This family belongs to Track B because file discovery, evidence selection and
termination are part of the outcome. Within a harness, models must receive the
same capability surface. Comparisons across materially different harnesses
remain deployed-system comparisons rather than causal model or tool ablations.

## 4. Repetitions

Performance and quality require different policies.

The project has three deliberately separate study modes: the current
**Capability Sweep**, a later **Quality Stochasticity Study**, and a later
**Performance and Reliability Study**. Their questions, repetition policies,
failure model and reporting boundaries are specified in
[`study-modes.md`](study-modes.md). The current small-sample screening data must
not be presented as a tail-latency or failure-rate study.

### Performance screening

Start with one explicitly cold run and one immediate warm run per model. Keep
cold-start latency separate from warm inference performance. Add two warm runs
only when configurations are close enough to affect a decision or measurements
look unstable. Reserve five measured warm repetitions for finalists,
publication-grade claims or cases where uncertainty remains material.

Report the number of runs and retain every raw measurement. Once enough
replicates exist, report at least the median and spread instead of hiding
outliers in a mean.

### Quality

- With temperature zero or a fixed seed, start with the predeclared quality
  candidate. Repeat only if the runtime still shows meaningful variation.
- With sampling or an agent loop, use several runs and report success rates and
  variation.
- Performance-only repetitions never replace a predeclared quality candidate
  after its result is known.

A fixed matrix such as "five runs times every task times every model" is not a
goal in itself. Replicates should quantify uncertainty, not merely consume
compute time.

## 5. Evaluation

Evidence priority for open-ended summarization and general-knowledge answers:

1. deterministic verification
2. a source-grounded, dimension-level rubric
3. blinded evaluation by the interactive Codex session
4. an optional anonymized pairwise tie-break

For each judgment, record the available judge identity, prompt, ordering,
versions and timestamp. The local runner calls no paid judge API. It creates an
anonymized judge bundle that is evaluated here only after the user explicitly
requests it. Pairwise comparisons with randomized response order supplement
close or inconsistent scalar scores.

Report results by task class first. Create a composite score only with explicit
and documented weights. Pareto fronts and constraint filters are more useful
for model selection:

- highest quality below a maximum latency
- highest success rate below a memory limit
- fastest configuration above a minimum quality

## 6. Context scaling

Context length matters, but it initially belongs in a controlled performance
subsuite instead of becoming another dimension of every quality task. Otherwise
the experiment matrix expands too quickly.

Possible stages are 1k, 4k, 8k and later 16k tokens. Determine token counts
with the tokenizer used by the actual model; character or word counts are not
reliable substitutes.

## 7. Protection against biased results

- Development cases are used to build prompts and the harness.
- Holdout cases are opened only for the actual comparison.
- Model responses are anonymized before human or judge evaluation.
- Errors, timeouts and invalid outputs remain data points and are not silently
  discarded.
- Task data is checked for licensing constraints, and private content does not
  enter the public repository.
- Every aggregate remains reproducible from raw data.
- A tracked manifest selects exactly one canonical comparison per case. This
  prevents a newer rerun from silently changing historical aggregate evidence.
- Controlled performance runs require an idle system. Known applications that
  use Ollama must be stopped, Ollama's loaded models cleared, and unexpected
  model activity monitored during the run.

## 8. Current implementation and next steps

Coding Track A now has a cross-case v0.1 report over three tasks and five local
deployments. Coding Track B has entered its implementation phase without model
execution. A shared draft protocol selects the PHP API-migration and JavaScript
async-cache cases, fixes permissions and budgets, and reports two harness
families separately. The project mini-harness uses a strict JSON action loop and
splits local inference from candidate-code execution. The external adapter pins
Pi package version 0.84.4 and its npm integrity, disables discovered resources
and permits only candidate-visible reads, allowed existing-file writes and the
exact public-test command. Pi live execution remains blocked on a validated OS
or container sandbox.

The frozen summarization v0.1 slice now contains:

1. three frozen English-to-German summarization benchmark cards
2. a streaming Ollama client
3. persisted run metadata and raw responses
4. deterministic constraint checks
5. anonymized single-run and multi-model judge bundles
6. interactive Codex evaluation against a fixed JSON Schema
7. cold/warm comparison orchestration with adaptive repetitions
8. a sanitized aggregate JSON index and Markdown report generated from an
   explicit canonical-comparison manifest

The slice has run successfully with a negative control and four realistic
models. Its first jointly judged quality comparison is complete. The initial
timing comparison is diagnostically useful but confounded by background Ollama
activity. A subsequent controlled rerun completed without observed unrelated
model activity and now provides the first usable performance screen. A second
quality evaluation preserved the ranking but exposed output variation at
temperature zero for two of four models, confirming that runtime-level
determinism must be measured rather than assumed.

The initial general-knowledge slice contains four German explanation cases with
judge-only references. The foundation confidence-interval comparison is
complete and proved useful for reliability but weak for discrimination among
valid deployments. A frozen hard companion now transfers the same concepts to
conflicting observational and randomized evidence. The controlled comparison
and blinded judgment on that transfer case are complete. Its 25-point
compliant-score range confirms that applied transfer is substantially more
discriminative than the foundation item's two-point range. The controlled mRNA
mechanism execution is complete with four formally compliant candidates; its
blinded semantic judgment is also complete. It produced one excellent response
and three good responses while exposing domain-specific mechanistic errors.
The interest-rate case has completed its controlled four-model execution with
four formally compliant warm candidates and its cognitively blinded judgment is
complete. Qwen 3.6 led both quality and warm wall time, so no adaptive repeats
were required. The comparison entered the canonical aggregate only after all
four scores and the required pairwise decision were frozen.

The first aggregate currently contains seven judged cases. Final scores include
invalid outputs and rubric caps; a separate compliant mean excludes responses
that failed completion or deterministic constraints. This distinction keeps
workflow reliability visible without discarding the quality of valid answers.
Warm wall time and output throughput remain separate columns rather than being
folded into quality. Raw artifacts stay Git-ignored, while the derived index,
selection manifest and Markdown overview are tracked and contain no candidate
IDs, run IDs, prompts, sources or raw responses.

The next general-knowledge block is frozen as Hard Knowledge v0.2 before any
execution. Its six transfer cases cover medical screening, antibiotic
resistance, renewable-electricity matching, distributed payment reliability,
ML evaluation leakage and RAG grounding. A machine-readable suite manifest
predeclares the exact case order, balanced within-case model orders, fixed
inference settings, environment gate, adaptive repetition policy and aggregate
rules. All six cases must remain in the primary block aggregate, including
invalid or capped outcomes. See `docs/hard-knowledge-v0.2.md`.
