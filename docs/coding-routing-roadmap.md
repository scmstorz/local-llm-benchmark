# Coding and Capability-Aware Routing Roadmap

## Status and scope

This document records a long-term research and implementation direction. It is
not part of the active Hard Knowledge v0.2 protocol and does not authorize an
immediate model router, a universal task-difficulty score or a large coding
benchmark matrix.

The current project phase remains the Capability Sweep. Its first coding phase
is complete as a deliberately small, reproducible Track A slice. The initial
`pagination-cycle-guard` task covers a Python bug fix and exposed both an
artifact-format floor and a verifier gap. The second
`async-cache-coalescing` task adds dependency-free JavaScript feature work with
asynchronous concurrency and invalidation races. The third
`php-payment-result-migration` task adds a framework-neutral PHP 8.4 API
migration across two collaborating writable classes, typed contracts,
payment-state transitions, retry semantics and idempotency. All three use
frozen repository fixtures and deterministic public plus hidden verification.
The JavaScript case's first excluded Ornith smoke reached both verifier layers
but failed the JavaScript behavior contract, reinforcing that capability
observations are task-and-system specific rather than transferable from one
coding case.
The post-smoke comparison was preregistered across the same five deployment
identities in `EDACB` order and executed with 0/5 verified successes. Qwen 3.8
was closest with 10/12 deterministic checks. Its one-attempt-per-model design
belongs only to the Capability Sweep; reliability and stochasticity remain
later studies. The PHP case is red-to-green validated. Its first excluded
Ornith smoke failed the whole-file output contract before tests despite
plausible-looking code. A separately labeled code-byte-identical transport
diagnostic passed all twelve deterministic checks, demonstrating the
difference between code semantics and harness compatibility without promoting
the malformed source outcome. Its frozen `BCEDA` comparison is now complete
with 0/5 strict successes. The preregistered diagnostic confirmed Ornith at
12/12, and exploratory post-hoc byte-preserving audits confirmed Qwen 3.8 and
Glimmer while exposing invalid PHP from Qwen 3.6. This case therefore measures
both code semantics and harness compatibility, which must remain separate.

The cross-case Track A v0.1 report now preserves all three primary matrices and
their different evidence layers. Track B implementation has begun with a
shared unfrozen protocol and two separately identified harnesses. The first
pilot subset contains the PHP migration, where direct tool writes can remove a
known transport floor, and the JavaScript async-cache case, where public-test
feedback may expose a genuine behavior error. Pagination is deferred until the
harnesses are stable and must then use verifier v1.2.

The project mini-harness is implemented as an explicit state machine. It
persists one pending Ollama request at a time, and model calls are a separate
operation from parsing actions, modifying the workspace or executing tests.
The second adapter pins `@earendil-works/pi-coding-agent@0.84.4`, its lockfile
integrity, CLI arguments and a benchmark-policy extension. The macOS pilot now
adds a run-specific deny-by-default Seatbelt profile. Eleven executable
no-inference checks validate file boundaries, symlink handling, exact writes,
process inheritance, process filtering, offline Pi startup, external-network denial and the single
local Ollama exception. Pi execution and hidden final verification are separate
commands, so the model-facing process never receives the hidden verifier.
Apple deprecates `sandbox-exec`; this backend is therefore versioned and
replaceable rather than treated as a permanent portable sandbox.

The first excluded PHP smoke pair is complete. The strict mini-harness stopped
at fenced-JSON protocol errors before any tool use. Pi crossed the transport
boundary, changed only the two allowed files and produced code that passed all
twelve deterministic checks. It did not satisfy the overall outcome contract:
the passing public test occurred in working turn 12, and the frozen policy
aborted the next turn before a normal final response. This is preserved as
verifier success plus invalid agent termination, not relabeled as verified
success. The first proposed correction was one tool-free settling turn. A
subsequent methodology review rejected any low normal turn ceiling because Pi
and Mini do not define turns equivalently and user value depends on verified
completion, time and resources rather than interaction rounds.

Track B v0.2 therefore records agent turns without using them as a normal
success limit. Wall time, total output tokens, exact path permissions,
operation-specific tool budgets and Mini protocol errors bound the run. Mini
v0.2 also passes a versioned JSON schema through Ollama's structured-output
`format` field instead of relying on prompt-only JSON compliance. Both pilot
cases passed no-inference Mini request generation and all eleven Pi Seatbelt
checks. The diagnostic v0.1 smokes will not be rerun after these changes.

The first measured Pi sweep showed that the total-output ceiling itself can
distort a capability screen: three JavaScript trajectories reached 12,000
tokens while substantial active time remained. Draft Track B v0.3 therefore
uses active task time as the primary user-facing capability budget. A provider
timeout still detects a stuck individual request. Turns, tokens and ordinary
tool effort are recorded rather than treated as success thresholds. Exact path,
command and sandbox restrictions remain hard safety boundaries; generous
operation counts remain only as emergency loop safeguards. Explicit token or
cost constraints can return later as independently named experimental
conditions in routing and efficiency studies.

## Long-term question

The project should eventually answer more than which model has the highest
average score:

> Which deployment configuration is sufficient for this task under these
> execution and verification conditions, and which sufficient configuration
> produces a verified successful outcome with the least total cost or time?

The preferred term is **Least-Cost Sufficient Configuration**, not merely
Minimum Sufficient Model. The experimental object includes the model and the
system around it:

```text
Task
× Model
× Quantization
× Runtime
× Harness
× Tools
× Context
× Reasoning and token budget
× Verifier
× Run
→ Distribution of outcomes
```

A smaller model is not automatically cheaper. It may produce more tokens,
invoke more tools, repeat tests, consume more wall time, fail, or require
escalation. Total trajectory cost matters.

## Optimization objective

The eventual constrained optimization problem is conceptually:

```text
minimize total expected cost or time
subject to verified success probability meeting the task-specific requirement
```

Cost may include:

- inference or compute time
- input and output tokens
- memory and, when measurement is credible, energy
- agent steps and tool executions
- test, build, browser, database or sandbox runtime
- retries and rollback work
- escalation to another model
- failure cost and computer opportunity cost

Primary reports keep quality, reliability, latency, resource cost and
trajectory effort separate. Cost per verified successful outcome is an
additional operational metric, not a universal composite leaderboard score.

## Difficulty is an empirical relationship

Tasks will not receive a claimed objective difficulty label such as easy,
medium or hard. Observed success depends on the entire configuration:

```text
P(success | task, model, harness, tools, context, budget, verifier, runtime)
```

Task families and descriptive features remain useful inputs. The empirical
capability boundary is derived only after several configurations have been
tested.

## Task description

### Task families

Initial families may include:

- localized code edit
- bug fixing
- feature implementation
- unit or integration test generation
- refactoring
- dependency upgrade or API migration
- performance optimization
- security remediation
- documentation
- repository exploration
- architecture change
- configuration or build change

Families organize the corpus but do not determine the required model class.

### Pre-run task capability profile

Features available before model selection may include:

- estimated change scope
- expected locality or repository-wide context requirement
- specification clarity
- reasoning and planning requirement
- dependency depth
- required tools and permissions
- verifier and feedback strength
- language and framework familiarity
- expected autonomy length
- risk, reversibility and failure cost

These are descriptive and versioned. They are not a validated universal
difficulty metric.

### Realized trajectory features

Features observed only during execution must be stored separately to prevent
information leakage into a pre-run router:

- agent steps and tool calls
- repeated tool calls or repeated identical failures
- files read and files changed
- test, build, lint and type-check runs
- verifier failures and time to first successful verification
- retries and rollbacks
- diff size and diff churn
- input, output and total tokens
- context consumption and growth
- wall time
- model changes or escalation events

The schema must distinguish `pre_run_task_features` from
`observed_trajectory_features`. A post-run observation such as actual files
read must never be represented as information available to the initial router.

## Three benchmark tracks

### Track A — Model capability

Question: How well does a model solve a task without complex agent
orchestration?

Hold the prompt, limited tooling, context, budget and evaluation constant.
This includes the current summarization, knowledge and reasoning work as well
as later bounded coding tasks.

The initial coding protocol supplies the complete declared repository snapshot
in one prompt. Models receive no tools, browsing, test feedback or retry. Its
immutable v1 contract requires one Git-style unified diff. The separately
versioned v1.1 contract requires strict complete-file replacement envelopes so
code-repair behavior can be measured without Git hunk serialization. The
controller installs either artifact only in a disposable fixture copy and
reports a boolean verified outcome rather than a synthetic partial-quality
score. Outcomes from the two contracts remain separate.
Verifier v1.2 closes the known start-cursor gap without rewriting v1.1
evidence. The second and third coding cases reuse the whole-file transport
while varying language, task family, writable scope and failure surface.

### Track B — Agentic capability

Question: How well does the same model work inside the same agent system?

Hold constant:

- harness and harness commit
- tools, permissions and sandbox
- context strategy
- token and time budgets
- retry and stop rules
- verifier and verifier version

Vary the deployment configuration. Evaluate the verified outcome and the full
trajectory rather than only the final prose or patch.

The coding tasks will later be executed under two separately versioned
Track B harness families:

1. **Pinned Pi:** an existing production-oriented coding agent with its exact
   version, system prompt, provider adapter, tools, permissions and context
   policy frozen.
2. **Project mini-harness:** a deliberately small model-independent loop with
   a narrow action protocol and only the tools required by the benchmark.

These answer complementary questions. Pi measures practical fit inside a real
external harness. The mini-harness provides a transparent controlled baseline
whose loop and failure behavior are fully inspectable. Their outcomes remain
separate and are never pooled as if `harness` were constant. OpenCode is a
later third harness candidate after the first two are stable. Its qualification
is now specified in
`tasks/coding/track-b/opencode-qualification-card-v0.1.json`; the card does not
prequalify the package or authorize inference.

### Track C — Capability-aware routing

Question: Which routing policy reaches a required verified success rate with
the least total cost or time?

Later baselines may include:

- always use the smallest deployment
- always use the strongest deployment
- static rule router
- small-to-medium-to-large cascade
- learned pre-run router
- dynamic trajectory router

Track C begins only after Tracks A and B provide enough repeated, verified
outcomes.

## Verified success

Coding benchmarks prefer deterministic verification over an ungrounded judge
score. Runtime completion, output validity, verification and semantic quality
are separate states.

Evaluation priority:

1. deterministic verifiers
2. requirement-grounded semantic rubrics
3. one fixed strong LLM judge
4. human calibration samples

Possible verifier layers include:

- a new regression test fails on the unmodified baseline
- the regression test passes after the patch
- protected existing and hidden acceptance tests remain green
- build, linter and type checker pass
- required changes exist
- prohibited files, tests or assertions were not weakened
- the patch stays inside allowed scope

Track A verifiers execute model-generated code. A disposable directory limits
state contamination but is not by itself a security boundary. Runs initiated
through Codex inherit the surrounding execution sandbox. Any later standalone
or published runner must use an explicitly documented OS or container sandbox
before accepting untrusted third-party patches.

Tests are evidence only to the extent that they cover the requirement. Hidden
or protected tests reduce benchmark gaming. High-risk security or architecture
tasks may require additional semantic review even when all tests pass.

Verifier strength has direct operational value. A reliable verifier permits a
more aggressive attempt with a smaller deployment because an insufficient
result can be detected and escalated. A false pass creates a silent failure and
is more dangerous than a detected model failure.

## Outcome and failure model

Each attempt preserves raw data and at least separates:

```text
execution_status:
  completed
  infrastructure_failed

output_status:
  valid
  malformed
  empty

verification_status:
  passed
  failed
  unavailable

task_status:
  verified_success
  failed
  unscored
```

Failure codes extend the general study-mode taxonomy:

- timeout, runtime crash, out of memory or model-load failure
- empty or malformed output
- tool failure
- maximum steps exceeded
- repeated failure or stalled trajectory
- tests, build, lint, type check or verification failed
- unacceptable requirement-grounded quality

No failed attempt disappears from aggregates. Technical performance among
successful runs and the probability of a verified success remain separate.

## Success thresholds and uncertainty

"Good enough" is task-dependent. Reliability requirements depend on risk,
verifier strength, reversibility and failure cost. A README edit and an
authentication refactor should not share an automatic universal threshold.

Observed point estimates are insufficient for a high reliability claim. A
configuration should not be called sufficient for a 95 percent requirement
merely because a small sample happened to produce 96 percent success. Later
decisions should report uncertainty and may require a lower confidence or
credible bound to exceed the required threshold.

The repetition policy in [`study-modes.md`](study-modes.md) remains applicable.
High thresholds and rare failures require substantially more attempts than an
exploratory five-run quality study.

## Least-Cost Sufficient Configuration

For an adequately sampled task or task class:

1. estimate verified success and its uncertainty for each fixed configuration
2. reject configurations that do not meet the task-specific reliability rule
3. compare remaining configurations on total expected time, resource cost and
   other declared constraints
4. report the non-dominated sufficient configurations
5. select a least-cost configuration only for an explicitly defined cost
   function and operating scenario

The result is empirical and versioned. It may change with a new model revision,
quantization, harness, verifier, context strategy or runtime.

## Escalation policies

A dynamic cascade may later use signals such as repeated failed tests,
re-reading the same files, growing context without progress or repeated tool
errors to escalate from a smaller to a stronger deployment.

Every cascade is itself a versioned experimental configuration. It must define:

- whether the stronger model starts fresh or receives prior trajectory state
- whether it inherits the failed patch and context
- what work may be rolled back
- which costs from earlier attempts are retained
- when escalation and termination occur

Under-routing and over-routing have asymmetric costs. Under-routing may cause
failure, retry and additional latency; over-routing may waste time and
resources while still succeeding. Risk-sensitive policies must encode that
asymmetry explicitly.

## Router evaluation

Future routing reports may include:

- verified success and failure rates
- P50 and sample-qualified tail time to verified success
- tokens and total resource cost
- agent steps and tool calls
- escalation rate and models used per task
- cost per verified successful outcome
- under-routing and over-routing counts or costs

An offline oracle can provide a comparison ceiling after configurations have
been tested, but it must not select models from lucky single runs. Oracle and
real routers need distributional estimates, and routing policies need separate
development and holdout tasks to avoid memorizing known outcomes.

Routing regret is the declared difference between a real policy and the oracle
under the same success requirement and cost definition.

## Data-model direction

The existing run records already preserve task and model identity, raw
artifacts, prompts, harness revision, runtime settings and performance. Coding
runs will extend them without breaking non-coding task classes.

Planned fields include:

```text
task_id
task_family
task_version
pre_run_task_features
model_name and digest
quantization
runtime and runtime_version
harness_commit
prompt_version
context and reasoning configuration
token, step and time budgets
tools and permissions
verifier_id and verifier_version
run_id and timestamps
warmup_or_measured
performance metrics
observed_trajectory_features
execution, output, verification and task status
quality dimensions
failure stage and failure code
routing_policy and escalation events, when applicable
```

The same stable task ID must be comparable across models and declared
conditions. Raw attempts remain primary evidence; aggregates are reproducible
derivatives.

## Staged implementation

### Current phase

Complete the general Capability Sweep and Hard Knowledge v0.2 unchanged.

### Coding Phase 1 — small vertical slice

- choose one language and ecosystem first
- prepare approximately 8–12 personally relevant, strongly verifiable tasks
- cover a few families such as localized bug fixes, small features,
  refactoring and build configuration
- freeze repository revisions, task specifications and verifier behavior
- run a small set of local deployments under one bounded harness
- answer which local configuration is sufficiently good for these concrete
  task classes

### Coding Phase 2 — controlled agent comparison

- use one identical harness, tool set, permission model and verifier
- add event-based trajectory recording
- compare models on verified outcomes and trajectory effort
- select a small discriminative subset for repeated success-rate studies

### Coding Phase 3 — descriptive sufficiency map

- estimate success distributions on adequately repeated tasks
- relate observed capability boundaries to pre-run task profiles
- identify where features fail to predict model need
- report least-cost sufficient configurations only within measured scope

### Coding Phase 4 — routing baselines

- compare always-small and always-strong baselines
- add one simple small-to-strong cascade
- measure total time, cost, success and escalation behavior
- define an offline oracle and routing regret carefully

### Later research

Only after enough evidence exists should the project consider a learned
pre-router or dynamic trajectory router.

## Explicit non-goals for now

- no complex machine-learned router
- no universal 1–10 difficulty score
- no hard-coded `easy → small` and `hard → large` rules
- no universal composite leaderboard score
- no P99 claim from a handful of runs
- no attempt to implement every coding taxonomy
- no reduction of the benchmark lab to coding alone
- no claim to find the globally optimal router across all tasks and systems

The near-term objective is narrower:

> Build the infrastructure to reproducibly determine which local deployment
> configurations are sufficiently good for a small number of real task classes.
