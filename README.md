# Local LLM Benchmark Lab

A reproducible benchmark suite for answering a practical question:

> Which local LLM deployment is good enough for a specific real-world task,
> and what quality, latency, reliability, and system trade-offs does it make?

The suite runs models through [Ollama](https://ollama.com/) on one local
machine. It currently covers German-language summarization, difficult
knowledge explanations, source-grounded professional writing, direct coding,
agentic coding, and read-only log incident analysis.

This is a personal benchmark lab, not a universal leaderboard. Its unit of
comparison is a deployed system, not a model name in isolation:

```text
task × model artifact × quantization × Ollama version × hardware/OS
     × context × inference settings × prompt × harness × verifier
```

## Why this project exists

Public benchmarks rarely answer the questions that matter in daily work. A
model can be excellent at summarizing a paper and weak inside a coding agent;
another can be fast enough to become the better default despite a small quality
gap. Quantization, runtime, context length, output protocol, tools, and
verification can change the result again.

This project therefore keeps four outcome layers separate:

- **quality** — is the answer accurate, complete, useful, and well calibrated?
- **performance** — how long did successful generation or task completion take?
- **reliability** — did the runtime and output contract complete successfully?
- **trajectory** — for agents, how many turns, tools, tests, retries, and tokens
  were needed?

It deliberately does not combine them into one opaque benchmark score.

## Current scope

### Track A: direct model capability

The model receives one frozen prompt without an agent loop.

- 3 English-to-German article and research-paper summaries
- 10 difficult German knowledge and transfer questions
- 2 German source-grounded professional-writing tasks
- 3 deterministic coding fixtures in Python, JavaScript, and PHP

### Track B: complete agent systems

The task and verifier remain fixed while the complete harness changes.

- a project-owned minimal JSON-action harness
- Pi coding agent, exactly pinned to version `0.84.4`
- 3 coding tasks with public and candidate-hidden tests
- 3 synthetic, multi-file log incident investigations with read-only tools

OpenCode has a qualification card but is not yet admitted to measured runs.

### Current and planned studies

Most current results are capability screens with one observation per cell. Two
two-model, two-case quality-stochasticity studies are now complete: one on
summary and source-grounded writing, and one on difficult general knowledge.
Separate study modes cover:

- quality stochasticity, with two initial repeated studies complete;
- performance and reliability distributions, with v0.1 frozen for Qwen 3.8
  and Ornith;
- context scaling;
- multi-model collaboration;
- eventually, capability-aware model routing.

The routing goal is not to use the strongest model everywhere. It is to find
the smallest or fastest system that reaches a task-specific verified-success
threshold, with escalation when a strong verifier detects failure.

## Selected findings

These findings describe the tested local configurations and task set. They are
not claims about model families in general.

| Evidence block | Main observation |
| --- | --- |
| 15-case direct text cohort | Gemma 4, Muse Glimmer, and Qwen 3.8 were tightly grouped at the top; Gemma had no hard output failures. |
| 13-case Ornith comparison | Ornith combined the highest observed mean quality with Qwen-3.6-like warm latency; Glimmer still won more individual cases. |
| Repeated German text quality | Glimmer won 5/5 METR-summary pairs; Ornith won 5/5 source-grounded-writing pairs and avoided Glimmer's recurring historical/current claim error. |
| Repeated difficult knowledge | Qwen 3.8 and Glimmer split direct pairs 5–5; Qwen had the markedly narrower score ranges and the safer observed quality floor. |
| Performance and reliability v0.1 | Both Qwen 3.8 and Ornith completed 40/40 requests; Ornith had 22% lower controlled median wall time and 29% higher controlled median decode throughput. |
| Agentic coding with pinned Pi | Qwen 3.8 was the only model to verify all 3/3 Python, JavaScript, and PHP tasks. |
| Pi versus the Mini harness | Pi verified 9/15 cells and Mini 6/15, but opposite task-model interactions rule out a universal harness ranking. |
| Agentic log analysis | All 27 completed reports found the central incident mechanism, yet only 1/30 satisfied the entire deterministic semantic contract. |

The last result is especially important: a strict structured verifier and a
human or fixed-LLM review of free-text claims measure different things. A model
can diagnose the central problem correctly while omitting required evidence
roles, overstating a claim, or violating an output contract.

Start with the curated reports:

- [direct text results](reports/challenger-sweeps/september-2026-model-cohort-quality.md)
- [Ornith late-challenger study](reports/challenger-sweeps/ornith-1.5-35b-quality.md)
- [repeated German text quality study](reports/quality-stochasticity/text-quality-v0.1.md)
- [repeated difficult-knowledge study](reports/quality-stochasticity/knowledge-quality-v0.2-analysis.md)
- [Performance and Reliability Study v0.1 interpretation](reports/performance-reliability/performance-reliability-v0.1-analysis.md)
- [Performance and Reliability Study v0.1 protocol](docs/performance-reliability-v0.1.md)
- [Coding Track A](reports/coding/coding-track-a-v0.1.md)
- [Pi versus Mini agentic coding](reports/coding/track-b-pi-vs-mini-system-comparison-v0.3.md)
- [agentic log incident sweep](reports/agentic/log-incident-capability-sweep-v0.5.md)
- [log-report grounding audit](reports/agentic/log-incident-capability-sweep-v0.5-quality-audit.md)

## Methodological rules

- Store every raw run; derive reports later.
- Record exact model tags and digests, runtime version, inference parameters,
  prompt and task versions, and harness configuration.
- Separate cold start from warm inference.
- Keep runtime success, output validity, verifier success, and judged quality
  as distinct fields.
- Use deterministic verification whenever the task permits it.
- Use source-grounded rubrics for open-ended answers.
- Freeze task, prompt, rubric, execution order, and model identities before a
  measured comparison.
- Rejudge newcomers jointly with exact incumbent responses instead of comparing
  scores produced in different judge sessions.
- Never report P90, P95, P99, or reliability probabilities from tiny samples.
- Preserve failures and interrupted attempts instead of silently dropping or
  retrying them.
- Keep development cases separate from future private holdouts.

All quality rubrics use a 0–100 scale, but their category weights are
task-specific. A cross-task mean is only a descriptive summary of this personal
task mix, not a universal intelligence score.

See [benchmark design](docs/benchmark-design.md),
[study modes](docs/study-modes.md), and the
[coding/routing roadmap](docs/coding-routing-roadmap.md) for the full rationale.

## Requirements

- Python 3.11 or newer
- a local Ollama server
- at least one installed Ollama model
- Node.js 22.19 or newer only for the pinned Pi integration
- PHP 8.4 only for the PHP coding fixture
- macOS for the current Pi Seatbelt sandbox implementation

The core Python package has no third-party runtime dependencies.

## Installation

```bash
git clone https://github.com/scmstorz/local-llm-benchmark.git
cd local-llm-benchmark
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -e .
```

Make sure Ollama is running and pull a model you want to test:

```bash
ollama pull qwen3.6:35b-a3b-mxfp8
```

Model availability and memory requirements depend on your Ollama installation
and hardware. The model names in this repository are exact local deployment
identities, not installation recommendations.

## Quick start

The general-knowledge cases are fully reproducible from the public repository.
They ask the candidate to answer from internal knowledge while a frozen,
project-authored source dossier is reserved for evaluation.

Run one model on one case:

```bash
local-llm-benchmark run \
  --model qwen3.6:35b-a3b-mxfp8 \
  --case tasks/general-knowledge/dev/medical-screening-bayes/case.json
```

Compare several models with one explicit cold run followed by one warm run:

```bash
local-llm-benchmark compare \
  --models qwen3.6:35b-a3b-mxfp8 qwen3.8:27b-mlx \
  --case tasks/general-knowledge/dev/medical-screening-bayes/case.json
```

Raw requests, Ollama streams, responses, deployment metadata, deterministic
checks, and blinded judge bundles are written below `results/` and ignored by
Git. The runner never calls a paid judge API. Quality judgment is a separate,
explicit workflow.

For repeated quality studies, the additive v0.2 evaluation pipeline enforces
the order `scalar freeze -> pairwise freeze -> model reveal`. It validates each
judge result against the exact case schema, hashes both immutable freezes, and
only then reads private model mappings and performance data to generate
separate quality, reliability, variation, error, pairwise, and latency
aggregates:

```bash
python3 -m local_llm_benchmark.quality_evaluation_v02 init \
  --study-dir results/quality-stochasticity/studies/STUDY-ID

python3 -m local_llm_benchmark.quality_evaluation_v02 status \
  --study-dir results/quality-stochasticity/studies/STUDY-ID
```

See the [Quality Evaluation Pipeline v0.2](docs/quality-evaluation-v0.2.md)
for the complete result-file contracts and reveal workflow. The previously
published v0.1 quality study remains a historical, manually frozen evaluation;
it is not retroactively represented as a v0.2 pipeline run.

The completed second repeated-quality study is the
[General-Knowledge Quality Stochasticity Study v0.2](docs/quality-stochasticity-knowledge-v0.2.md).
It compares Qwen 3.8 with Muse Glimmer on one quantitative and one conceptual
transfer case, with five fresh repetitions per condition. Its preparation did
not call Ollama; the later live phase completed 20/20 measured units and used
Evaluation Pipeline v0.2 before reveal. See the public-safe
[interpretation](reports/quality-stochasticity/knowledge-quality-v0.2-analysis.md).

Inspect all commands:

```bash
local-llm-benchmark --help
local-llm-benchmark run --help
```

Run the dependency-free test set supported by a sanitized public clone:

```bash
python3 scripts/run_public_tests.py
```

The complete local research test suite additionally depends on the pinned Pi
installation, private source fixtures, and historical commits that are
intentionally absent from the clean public history.

## Recurring model onboarding

New models do not require runner changes or a new task-suite version. Register
the exact installed deployment without loading it or running inference:

```bash
local-llm-benchmark model-register --models \
  granite4.2:30b \
  nemotron-3.5-lightning:30b-mlx \
  gemma4:31b-mlx
```

Registration stores the Ollama tag, digest, metadata, and runtime version. If a
tag later points to a different digest, it becomes a new deployment identity
instead of replacing old evidence.

Run one deployment across the current 15-case direct-text manifest:

```bash
local-llm-benchmark suite \
  --model gemma4:31b-mlx \
  --suite tasks/capability-suite-v0.3.json
```

The complete suite includes copyrighted source material and personal writing
inputs that are intentionally not redistributed. A public clone can run the
general-knowledge subset immediately; summarization and source-grounded writing
cases require the private inputs declared in their case metadata.

Resume an interrupted append-only sweep without repeating completed cases:

```bash
local-llm-benchmark suite-resume \
  --sweep-dir results/sweeps/SWEEP-ID
```

See [model onboarding](models/README.md) for cohort manifests, challenger
bundles, lifecycle states, and retirement policy.

## Deterministic coding benchmarks

Validate a fixture and confirm that its intentionally incomplete baseline is
red:

```bash
local-llm-benchmark coding-check \
  --case tasks/coding/dev/async-cache-coalescing/case.json
```

Generate one direct, non-agentic Track A attempt:

```bash
local-llm-benchmark coding-run \
  --model qwen3.8:27b-mlx \
  --case tasks/coding/dev/pagination-cycle-guard/case-whole-file-v1.2.json
```

Candidate code is installed in a disposable fixture copy. Public tests and
candidate-hidden tests are recorded separately. Read
[the coding track documentation](tasks/coding/README.md) before executing
untrusted model output.

## Agentic coding

Track B compares complete systems rather than pretending the harness is a
neutral wrapper. The Mini harness and pinned Pi adapter use the same task
fixtures and final deterministic verifier, but differ in prompt, protocol,
tools, context handling, and recovery behavior.

Mini separates the Ollama call from action execution:

```bash
local-llm-benchmark coding-agent-mini-start \
  --model qwen3.8:27b-mlx \
  --case tasks/coding/dev/php-payment-result-migration/case.json

local-llm-benchmark coding-agent-mini-call \
  --run-dir results/agentic-runs/agentic-run-ID

local-llm-benchmark coding-agent-mini-step \
  --run-dir results/agentic-runs/agentic-run-ID
```

Repeat the final two commands as directed by the persisted state.

Install the pinned Pi integration separately:

```bash
cd integrations/pi
npm install --ignore-scripts
npm test
cd ../..
```

Prepare and qualify a Pi run before live inference:

```bash
local-llm-benchmark coding-agent-pi-prepare \
  --model qwen3.8:27b-mlx \
  --case tasks/coding/dev/php-payment-result-migration/case.json

local-llm-benchmark coding-agent-pi-sandbox-check \
  --run-dir results/agentic-runs/pi-agentic-run-ID
```

The live trajectory and hidden final verification are deliberately separate.
See the [pinned Pi integration](integrations/pi/README.md) and
[Track B contract](tasks/coding/track-b/README.md) before running them.

## Safety

Coding and agentic benchmarks execute candidate-generated code. Do not run
them directly on a trusted working tree. The suite uses disposable fixture
copies and separates model access from final verification, but a standalone
deployment must still provide an explicit OS or container sandbox.

The current Pi backend uses a deny-by-default, run-specific macOS Seatbelt
profile and an adversarial acceptance suite. Apple deprecates `sandbox-exec`,
so this is a versioned experimental boundary, not a permanent portable
sandbox.

## Repository layout

```text
local_llm_benchmark/  Python runner, adapters, verifiers, and reports
tasks/                Versioned cases, prompts, fixtures, and contracts
models/               Deployment catalog, lifecycle, and cohort manifests
capabilities/         Harness capability inventories and isolation profiles
integrations/pi/      Exactly pinned external Pi integration
tests/                Offline unit and qualification tests
reports/              Curated public-safe result artifacts
docs/                 Benchmark methodology and roadmaps
results/              Ignored raw runs and private evaluation bundles
data/private/         Ignored copyrighted and personal benchmark inputs
```

## Publication boundary

The public repository is exported from a richer local research repository.
Private source texts, raw responses and rendered private prompts, candidate
mappings, machine-specific run paths, personal inputs, screenshots, and
internal chronological notes are excluded. Sanitized aggregate experiment IDs
remain in curated reports for provenance. The export is generated from an
explicit allowlist and scanned before push.

See [PUBLICATION.md](PUBLICATION.md) for the exact boundary and
[RELEASING.md](RELEASING.md) for the reproducible, locally gated update
procedure.

## Releases and versioning

Project releases version public repository snapshots. Task, prompt, verifier,
harness and study-protocol versions remain independent immutable identifiers;
for example, a task protocol named `v0.5` does not imply project release
`v0.5.0`. See [CHANGELOG.md](CHANGELOG.md) for tagged release scope and
interpretation boundaries.

## License

Copyright 2026 Sacha Storz.

Project-owned code, documentation, prompts, synthetic fixtures and reports are
licensed under the [Apache License 2.0](LICENSE). Third-party dependencies,
model artifacts and externally published source material remain subject to
their respective terms; the project license does not relicense them.

## Status and limitations

- The project is experimental and currently optimized for one local macOS
  setup.
- Most result cells have `n=1`; they map observed capability, not reliability
  or latency tails.
- Interactive LLM judgment improves open-ended evaluation but remains a source
  of judge variance and possible identity inference.
- Development prompts and public verifier fixtures are not hidden test sets.
- Model, Ollama, and harness updates create new deployment conditions and must
  not be silently pooled with old results.

Contributions and issue reports are welcome once the public workflow has been
used outside the original environment.
