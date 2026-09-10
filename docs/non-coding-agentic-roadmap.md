# Non-Coding Agentic Benchmark Roadmap

## Status

Decision recorded on 2026-09-05. The immediate scope contains only the first
item below. Its three synthetic cases, deterministic verifier and two read-only
complete-system paths are implemented. The original v0.1 Mini/Pi paths and
excluded Qwen 3.8 smoke pair remain frozen. New `mini-log-v0.2` and
`pi-log-v0.2` paths select the common three-case protocol, passed no-inference
qualification and now have excluded live machinery results. A separate durable
measured-sweep controller has passed no-inference qualification; its exact
deployment cohort and balanced 30-cell order are now frozen before execution.

Offline task breadth adds two distinct cases: delayed retry-driven queue
amplification, and distributed clock skew with only partial recovery. They use
a new strict report contract and data-driven verifier v2. The checkout fixture
has an additive v2 representation so all three systems share one output and
verification protocol without changing any frozen v0.1 artifact. The three
references pass 42/42 checks. These cases and harnesses are qualified only for
separately frozen excluded smokes; they are not retroactively inserted into the
v0.1 pair and are not model results.

## Immediate priority: Agentic Log Incident Analysis

The next non-coding Track B task family will test whether a local deployed
system can inspect a frozen multi-file log fixture, reconstruct an incident,
distinguish causal evidence from distracting warnings and produce a bounded,
auditable incident report.

The first case should answer:

> Can the deployed model-and-harness system identify the correct incident,
> support its diagnosis with exact evidence and communicate uncertainty without
> access to a hidden answer key or external network?

### Intended fixture

- several immutable log files from multiple services;
- at least one rotated or chronologically discontinuous file;
- structured and unstructured log formats, such as JSONL and plain text;
- trace, request or correlation identifiers that cross file boundaries;
- timestamps whose ordering requires explicit timezone handling;
- plausible but non-causal warnings as distractors;
- one frozen causal chain and a small number of deliberately missing facts;
- synthetic or carefully sanitized content only, with no host or production
  secrets.

The fixture must be restored into a fresh read-only task workspace for every
run. The agent receives no network access, shared mutable state, hidden
verifier path or earlier-run artifacts.

### Candidate output contract

Prefer one structured report with fields equivalent to:

```json
{
  "incident_window": {},
  "affected_components": [],
  "root_cause": "",
  "causal_chain": [],
  "evidence": [],
  "impact": "",
  "recommended_actions": [],
  "uncertainties": []
}
```

Each evidence item should cite a frozen file identifier and stable line or
event identifier. The contract should distinguish observed facts, inference
and unresolved uncertainty.

### Evaluation design

Use deterministic verification wherever the construct permits it:

- schema and parser validity;
- incident time bounds;
- affected component identifiers;
- required trace/request identifiers;
- existence and correctness of cited evidence;
- required and forbidden causal claims;
- unsupported-event count;
- final task success.

A source-grounded rubric may supplement deterministic checks for causal
explanation, prioritization, remediation quality and calibration of
uncertainty. It must not replace mechanically checkable evidence. The task card
must document the construct, proxies and known blind spots before the first
measured request.

### Agentic boundary and telemetry

The task is read-only but agentic: the system must decide which files and
events to inspect and when it has enough evidence. Record at least file reads,
search/tool calls, malformed or failed calls, repeated reads, turns, input and
output tokens, active wall time, termination reason and verified success.

Within one harness, compared models receive the same prompt, capability
inventory, tool schemas, permissions, context policy, time boundary and
verifier. Pi-versus-Mini results remain complete-system comparisons unless a
later experiment actually holds every other behaviorally relevant factor
constant.

### Execution sequence

1. Create and independently solve the fixture.
2. Freeze the task card, visible inputs, hidden reference and verifier.
3. Validate the verifier against the untouched fixture, an independent correct
   report and deliberate near misses.
4. Freeze the capability inventory and isolation profile for each participating
   harness.
5. Run one excluded smoke to qualify the new non-coding action/output path.
6. Freeze a small Capability Sweep before any measured request.
7. Preserve raw runs and publish only sanitized derived results.
8. Add targeted repetitions only when a named uncertainty justifies them.

This first slice is not a performance-tail, reliability-probability or online
research study.

### Implemented v0.1 vertical slice

The first case is `agentic.ops.checkout-pool-regression`. Six immutable files
mix JSONL and plain text, include one rotated log and use both UTC and `+02:00`
timestamps. The hidden answer separates a payment-service connection-pool
configuration regression from the traffic trigger, downstream checkout
failures and unrelated authentication warnings.

The final report uses a strict JSON schema. Thirteen essential deterministic
checks cover structure, UTC boundaries, affected scope, root cause, trigger,
citation integrity, the causal chain, critical evidence, distractor rejection,
bounded impact, remediation, uncertainty and unsupported claims. The
independent reference passes all thirteen. Nine deliberately damaged reports
or fixtures fail as intended.

`mini-log-v0.1` exposes only `read_file` for one of the six declared files and
`finish_report` for the final structured result. It has no filesystem-write,
shell, code-execution, browser, network, memory or delegation action. Every run
copies and re-hashes the fixture into a fresh workspace. Harness, prompt,
schema, capability inventory, isolation profile, implementation, case and
hidden-reference hashes are bound into the raw run record. Model requests,
actions and final hidden verification are separate durable commands.

The no-inference qualification passed 19 focused verifier, adapter and
qualification tests plus the complete 210-test repository suite. It contacted
neither Ollama nor a model. This is an application-level read-only boundary,
not a portable OS sandbox; that distinction is acceptable only because no
candidate-authored code or command is executable in this harness.

`pi-log-v0.1` provides the second complete-system path. It pins Pi 0.84.4 and
enables only Pi's native `read` tool. The model receives the file inventory but
not the log contents, chooses its own reads, and must place one unfenced JSON
object in the final assistant message. The controller does not repair prose,
Markdown fences or a malformed result. Native Pi events and a task-specific
policy audit retain turns, tool calls, failed calls, repeated reads, per-file
reads and token usage.

The Pi path uses two independent enforcement layers. A policy extension rejects
every tool except a path-checked read. A deny-by-default macOS Seatbelt profile
then permits only the resolved Node executable, read access to the prepared run,
private runtime writes and loopback access to port 11434. Nine real no-inference
acceptance checks passed: visible read, denied workspace write, denied hidden
ground-truth read, denied symlink escape, permitted private runtime write,
denied unlisted process, offline Pi startup, denied external TCP and permitted
local loopback. Candidate code was not executed and the candidate workspace was
not modified.

The first Seatbelt acceptance attempt was made inside the already sandboxed
development environment and failed before model contact because nested macOS
sandboxing changed the execution boundary. Repeating the identical command at
the intended host boundary passed all nine checks. The failed attempt is kept
as a control-layer observation, not a benchmark outcome or an automatic model
retry. Across both attempts, Ollama/model request count remained zero.

Current validation is 223 passing Python tests, five task-specific Pi/Policy
Node tests and twelve active tests in the pre-existing Pi integration suite;
its opt-in live transport test remains skipped. Pi-versus-Mini results will be
reported as complete-system comparisons: native `read` plus final-message JSON
is behaviorally different from Mini's `read_file` plus `finish_report`, even
though case, verifier, time boundary and unavailable capabilities are aligned.

### Frozen excluded qualification pair

The two one-attempt smoke plans use the same exact Qwen 3.8 deployment, model
digest, Ollama 0.33.2 runtime, case and inference settings. Their order is Mini
then Pi. They have no automatic or adaptive retry and are excluded from every
future measured aggregate. Verified success is not required to qualify the
machinery; a complete, preserved and machine-classified task failure is
interpretable, whereas an adapter or orchestration defect blocks sweep design.

`local_llm_benchmark.log_incident_smokes` is a durable state machine. `start`
creates only the ignored study record; `advance` performs preparation, action
processing, sandbox acceptance or hidden verification; `live` is the only
command permitted to contact a model; `cleanup` unloads the selected model and
requires an empty postflight; and `report` produces the public-safe JSON and
Markdown result from terminal raw records. A process interruption during Mini
or Pi live execution is retained as an inconclusive attempt, then cleaned up
without a retry before the pair may continue.

The live boundary has two independent admission conditions. The automatic gate
requires the frozen runtime and digest, no loaded Ollama model, two clean
process snapshots and two empty Ollama snapshots separated by 30 seconds. It
recognizes active Behat commands, `behat_test` environment workers, common test
runners, package test scripts and the known local Ollama applications. It does
not confuse an idle `mnemosyn_mcp.py` helper or router-only Behat infrastructure
with an active test run. Separately, `live` requires explicit confirmation of an
exclusive window because another development agent could start Behat after the
automatic observations have finished.

The real host preflight found four matching Behat-environment processes, one at
78.3% CPU, and stopped before its first Ollama call. Only sanitized rule IDs,
PIDs, CPU values, elapsed values and command hashes were emitted. No benchmark
study or model run was created. With the ten new plan/controller tests, current
Python validation is 233 passing tests.

### Offline-qualified v0.2 task breadth

A single synthetic incident can accidentally reward case-specific pattern
matching. Before interpreting a later model result broadly, the task family now
contains three different causal structures:

| Case | Primary construct | Central trap | Recovery evidence |
| --- | --- | --- | --- |
| `checkout-pool-regression` | configuration regression exposed by load | traffic and unrelated warnings mistaken for cause | rollback plus pool and endpoint health |
| `retry-queue-amplification` | delayed nonlinear retry amplification | downstream slowdown or loud TLS error mistaken for cause | retry rollback, queue drain and endpoint health |
| `clock-skew-partial-recovery` | distributed chronology repair | naïve timestamp sorting and premature closure | new traffic recovers but backlog remains |

All three cases now have a report-contract-v2 representation. The contract uses
`last_observed_utc` rather than claiming that the final observation is an
incident end, and adds an explicit recovery state with `full`, `partial` and
`not_observed` values. Exact event/file citations, a causal chain, rejected
hypotheses, impact codes, actions and uncertainties remain mandatory.

The v0.2 verifier is a new file rather than a rewrite of the v0.1 verifier
already bound into harness qualifications and smoke plans. Per-case ground
truth drives the same 14 essential checks. Two reference reports pass all 28
combined checks. Eighteen targeted negative cases demonstrate rejection of
cause/trigger swaps, omitted amplification, reversed clock chronology, missing
offset evidence, false full recovery, unsupported loss, wrong citation paths,
missing distractor counter-evidence, absent uncertainty, malformed reports and
fixture drift.

Separate Mini and Pi qualification artifacts bind implementations, report
schema, policies, tests, cards, tasks, manifests and hidden references by
SHA-256. Mini's selected-case-only boundary denies cross-case reads. Pi adds a
new selected-case policy while reusing the unchanged Seatbelt backend that
already passed 9/9 real host checks. Mocked v0.2 Seatbelt integration passes for
all three fixtures, but a fresh real acceptance remains mandatory for every
actual Pi run. Both records contain zero Ollama calls and authorize no measured
run.

The excluded v0.2 machinery pair used Qwen 3.8 on
`retry-queue-amplification`. Mini returned a valid report but passed only 11/14
checks. Pi passed fresh 9/9 real Seatbelt acceptance and completed normally, but
its leading prose made the strict final JSON invalid. Its embedded object would
still have passed only 10/14 in a non-official diagnostic. Both are interpretable
task/output failures rather than adapter failures.

The run report also preserves a protocol deviation: after one sandbox-denied
zero-token Mini record and one execution-session interruption during a later
Mini turn, a fresh run was started despite the frozen do-not-retry wording. The
partial stream was not reconstructed, inspected for selection or scored. This
does not enter measured evidence, but it prevents describing the smoke pair as
strictly one-execution-attempt compliant.

The remaining sequence is now:

1. run each frozen cell once and preserve every technical and task outcome;
2. generate the public-safe cross-case complete-system report;
3. interpret breadth cautiously before choosing any replication study.

### Durable measured-sweep controller

`local_llm_benchmark.log_incident_sweep` is additive: it does not alter either
v0.2 harness or the excluded smoke evidence. It requires the complete Cartesian
product of both complete systems, every selected deployment and all three
report-v2 cases. Preparation, Mini action processing, Pi Seatbelt acceptance,
hidden verification and model cleanup are independent checkpoints.

The `drive` command is intended for the actual long execution window. It keeps
one foreground process across all remaining cells instead of depending on a
new development-tool session for every model turn. Terminal cells are never
repeated. If the process is lost during a live adapter state, the raw attempt
is preserved and the cell is classified as an infrastructure/control failure;
the controller does not manufacture a replacement result.

The companion public report contains only identities, outcome layers,
deterministic check counts, failure types, trajectory counts, tokens and active
time. It excludes candidate reports, fixture contents, hidden references and
absolute paths. With one run per configuration, all timing summaries remain
descriptive and no reliability, stochasticity or tail-percentile claim is
allowed.

### Frozen measured design

The first measured plan selects the five `active_default` deployments from the
versioned lifecycle registry: Qwen 3.6, Qwen 3.8, Muse Glimmer, Ornith and
Gemma 4. Each deployment receives every incident exactly once under Mini and
once under Pi, producing 30 cells. Granite, Nemotron and retired GPT-OSS remain
outside this regular sweep under the already documented lifecycle rule.

The order was balanced before outputs existed. No model occurs consecutively;
model position sums range from 92 to 94, case sums from 154 to 156, and the two
complete systems occupy position sums 232 and 233. These controls reduce simple
order confounding but do not turn the system comparison into a causal harness
experiment.

The excluded [smoke report](../reports/agentic/log-incident-qualification-smokes-v0.2.md)
is public-safe and explicitly disallows model, speed or harness ranking claims.

### Measured v0.2 outcome and specification stop

The frozen sweep completed all 30 cells without a runtime, controller or agent-
termination failure. Its strict primary result is 0/30 verified successes.
Twenty-two reports reached the complete 14-check verifier: Mini produced 15/15
schema-valid reports and Pi produced 7/15. The other eight Pi responses all
contained JSON inside an outer response envelope, but an exploratory envelope-
only extraction still produced zero fully verified reports. Primary outcomes
were not changed.

Qwen 3.8 supplied the strongest partial evidence. Under Mini it passed 36/42
checks across the three cases, and all three cells within two checks of strict
success used Qwen 3.8. These are diagnostic counts, not normalized quality
scores. With one observation per system-model-case cell, the sweep does not
estimate reliability or quality stochasticity.

The required post-run human calibration found a specification-to-verifier
misalignment. Candidate-visible tasks explain `last_observed_utc` but never
define `start_utc`; the frozen verifier requires the first observed user-facing
impact. Twenty of 22 schema-valid reports failed that combined window check,
often after choosing a plausible earlier deployment, trigger or admission
event. The result is therefore retained as historical protocol evidence but is
not decision-ready evidence that the tested models cannot perform the task.

The next version must remain additive and must not rewrite v0.2 history:

1. define `start_utc` as the first supplied evidence of user-facing impact;
2. audit every hidden check for an explicit candidate-visible instruction;
3. preserve strict output-envelope compliance as its own observable outcome;
4. decide before execution whether a deterministic outer-envelope parser is
   part of the deployed system, and report strict compliance separately;
5. qualify all references plus targeted negative controls offline;
6. freeze a small v0.3 confirmation matrix before any more model inference;
7. only after confirmation decide whether a broader sweep or repetitions are
   warranted.

Do not start the quality-stochasticity or performance/reliability study on the
v0.2 task definition. The measured v0.2 timings are also descriptive only:
heavy Spotlight indexing was documented at launch.

### Corrected v0.3 representation

The validity repair is additive. Existing v0.2 definitions, raw runs and public
reports remain untouched. All three incidents now have a `case-v0.3.json` and
`TASK-v0.3.md`; their evidence fixtures and report-contract-v2 shape are reused
because neither caused the discovered alignment failure.

The v0.3 visible evaluation contract maps every essential verifier check to a
literal task marker. The verifier splits the former combined incident-window
criterion into `incident_start_utc` and `last_observed_utc`, yielding 15 checks.
The former is explicitly the earliest supplied event that demonstrates impact
to the reported user journey. Earlier deployment, configuration, trigger,
admission or internal-symptom events are not silently accepted as impact onset.
Recovery status is still assessed independently from the final observation.

Response handling is part of the deployed system rather than a post-hoc rescue.
The frozen normalizer accepts exactly one syntactically intact JSON object with
optional outer prose or a Markdown fence. It performs no key, value, quote,
comma or brace repair, and it rejects ambiguity. This creates two deliberately
separate results:

- `semantic_verified_success`: runtime and agent termination are valid and the
  normalized report passes all 15 essential checks;
- `strict_transport_compliance`: the final report used the requested bare-JSON
  transport without normalization.

Mini and Pi v0.3 share that outcome model, but remain complete deployed systems,
not a one-factor harness experiment. Pi remains pinned to 0.84.4 and reuses the
unchanged read-only policy and Seatbelt backend. Its capability boundary must
still pass fresh real acceptance before each future execution.

Offline qualification produced 45/45 reference checks across the three cases,
rejected targeted semantic and parser near misses, and passed 320 core Python
plus 21 active Node tests. Four plan tests bring the current Python total to
324. No Ollama call occurred. The next methodologically valid
step is not another full sweep. The implementation was committed first, then a
six-cell Qwen 3.8 matrix was frozen across both systems and all three cases. It
has no numeric success threshold because six single attempts cannot validate
capability or reliability; its gate is an explicit post-run audit of failure
attribution, criterion visibility and normalizer behavior. Execution remains
unauthorized until Behat and other Ollama consumers are stopped and the full
resource gate passes. Only that confirmation may determine whether a broad
v0.3 Capability Sweep is worth its runtime.

### Durable v0.3 confirmation execution

The confirmation plan was intentionally frozen before an execution controller
was added. A later user message authorized the six real cells after reporting a
clean machine. That authority is recorded in a separate artifact bound to the
frozen plan hash, so the original plan's withheld-authorization state remains
historically true rather than being edited after the fact.

The additive controller adapts the proven checkpoint lifecycle to Mini and Pi
v0.3. It validates the single Qwen deployment, both qualified harnesses, all
three cases, frozen artifact hashes and the separate authorization. Every cell
still receives a real resource gate; Pi still receives fresh Seatbelt
acceptance. Lost live processes become preserved infrastructure/control
failures and are never replaced by an unplanned retry.

The associated report path exposes runtime success, valid termination,
semantic verifier success, semantic verified success, strict transport
compliance, normalizer use, check coverage, trajectory counts, tokens and
descriptive time. It excludes raw candidate reports, log contents, hidden truth
and absolute paths. Five controller tests pass, including a mocked live boundary
that performs zero Ollama calls and a privacy canary. The full Python suite now
passes 329 tests.

### v0.3 confirmation result and v0.4 gate

The six frozen cells completed as an excluded specification confirmation. Five
runtimes and agent terminations were valid; the final Pi clock-skew cell reached
the predeclared 300-second active-time limit while producing its final answer.
The official result is 0/6 semantic verified successes, with four strict JSON
responses and one additional report recovered by the frozen normalizer.

The original timestamp repair worked: all four schema-valid reports passed the
separate incident-start, last-observation and recovery-status checks. The fifth
produced report held the same correct temporal values but failed the schema
before those checks ran.

Post-run human calibration found that v0.3 is still not ready for a broad model
sweep. The verifier silently treats human-readable scope values as hidden
controlled identifiers, requires an exhaustive reference event set where the
visible task asks for sufficient direct counter-evidence, and in one case
requires an event to be duplicated across roles and forces another event into
one hidden role despite visible guidance permitting a different direct role.
These are benchmark false negatives. Genuine system errors remain separately
visible:
three causal-chain misses, one schema-key error and one timeout.

v0.3 stays immutable and is not rescored. The next representation must be
additive v0.4. It should expose scope codebooks or accept semantic equivalents,
model rejected-hypothesis proof as predeclared accepted evidence groups, and
remove or explicitly document hidden multi-role and single-reference-role
requirements. Preserve the validated temporal wording, schema gate, response
normalizer and user-facing
timeout. Requalify offline and run another small confirmation before authorizing
any multi-model capability sweep.

### Additive v0.4 alignment repair

v0.4 implements the three post-confirmation repairs without changing any v0.3
artifact or official outcome. Scope matching now compares normalized lexical
tokens: case and separators are ignored, `and` is treated as glue and repeated
words collapse. No domain synonyms are invented, and a negative control proves
that adding another journey concept still fails.

Rejected-hypothesis truth now declares one or more accepted sufficient evidence
groups per required alternative. A candidate must attach every event from at
least one group, and every cited event must still exist in the selected fixture.
This accepts the valid counter-evidence observed in v0.3 without turning the
criterion into unrestricted prose judgment. A partial group remains a failure.

The clock-skew truth no longer requires the skewed-node rejection under both
root-cause and symptom roles, nor does it force the user-facing intermittent-
reject signal into a hidden reference role. The visible task now says explicitly
that one most-direct role is sufficient.

All three references pass 45/45 checks. Focused controls cover equivalent and
non-equivalent scope, alternative and insufficient counter-evidence, the single-
role clock reference, semantic near misses, schema failure and response parsing.
Mini and pinned Pi 0.84.4 have new v0.4 identities over unchanged read-only
capability boundaries. The full offline suite passes 363 Python and 21 active
Node tests; the opt-in live transport test remains skipped. No Ollama request
occurred. Commit this implementation before freezing the next small confirmation.

### Frozen v0.4 specification confirmation

The v0.4 implementation was committed at `e0ea63b` before the next experiment
was defined. The confirmation keeps the v0.3 six-cell structure: Qwen 3.8 runs
once on each of the three incidents under Mini and pinned Pi 0.84.4, in an
interleaved order, without retries or adaptive additions. It is explicitly
excluded from model-ranking, reliability, stochasticity and latency-tail
evidence.

The plan freezes the v0.4 task, verifier, Mini/Pi adapters, qualifications,
model digest, Ollama 0.33.2 runtime and controller inputs. Live execution is
separately authorized by the user's clean-window statement and still requires
the real 30-second empty-Ollama/process gate before every cell. Pi additionally
requires fresh Seatbelt acceptance. The 300-second active-time boundary and
40-read emergency safeguard remain, while agent turns and total output tokens
remain unlimited. Nine focused plan/controller tests pass offline.

### v0.4 confirmation result and v0.5 gate

All six frozen Qwen 3.8 cells completed technically under Mini and pinned Pi
0.84.4. The official outcome is 1/6 semantic verified successes and 4/6 strict
JSON transports. Mini contributed the one semantic success and was strict in
all three cases; Pi required outer-envelope normalization twice but completed
the clock-skew case that had timed out in v0.3. These are single attempts and do
not estimate either harness's reliability.

The three intended v0.3 repairs behaved correctly. Human calibration found the
next alignment boundary, however. Free-text forbidden-fragment matching is
negation-blind; exact normalized scope equality rejects correct component
specialization; and the visible rejected-hypothesis wording does not state
clearly whether an exact event citation in `reason` must also appear in
`evidence_ids`. Genuine causal-chain omissions and misordering remain cleanly
separable in positions 2, 5 and 6.

v0.4 stays immutable and is not rescored. Do not start its broad model sweep.
Additive v0.5 should move machine-scored identity back to visible canonical
fields, make evidence attachment semantics explicit and remove lexical claim
polarity inference from deterministic scoring. Preserve the already validated
time, evidence-role, normalizer, isolation and timeout behavior, qualify
targeted controls offline and use another small confirmation gate.

### Additive v0.5 controlled-claim repair

v0.5 implements that gate as a new representation; it does not rewrite the
v0.4 confirmation. The task for each incident now publishes complete exact-ID
codebooks for both scope fields and every other machine-scored categorical
field. The candidate must select the canonical service and journey IDs exactly.
Compatible component detail remains expressible in diagnosis prose or event
citations, so the machine field has one stable meaning instead of an implicit
string-equivalence policy.

Rejected-hypothesis evidence is now structurally local. Only event IDs placed
in that hypothesis entry's `evidence_ids` array satisfy the deterministic
counter-evidence requirement. IDs in `reason`, in the causal chain, in the
general evidence list or under another hypothesis do not count. The visible
instruction and a reason-only negative control make this boundary testable
before any model sees the task.

The negation-blind forbidden-fragment check is removed. Its replacement,
`controlled_code_integrity`, validates that scope, diagnosis, triggers,
rejected-hypothesis labels, impact, recommendations and uncertainty labels all
come from their visible codebooks. It deliberately does not classify the truth
value of prose. Free-text source grounding is a mandatory supplemental human or
fixed-LLM review outcome and must not be collapsed into deterministic semantic
success. This means a structured report can pass all 15 deterministic checks
while still failing the supplemental review; the distinction prevents both
false precision and silent ungrounded claims.

The three references pass 45/45 checks. Tests prove that exact scope IDs pass,
wrong but allowed scope IDs fail the semantic scope check, unlisted codes fail
integrity, a negated unsupported phrase no longer causes a false negative, a
positive unsupported prose claim is transparently deferred, and an event named
only in a rejection reason does not count as attached evidence. The prior
temporal, causal, evidence-role, response-normalization, timeout and read-only
boundaries remain unchanged. Mini and pinned Pi 0.84.4 receive versioned v0.5
adapters and require the supplemental-review flag at load time.

Offline qualification passes 409 Python tests and 21 active Node tests; the one
opt-in live transport test remains skipped. No Ollama request or model inference
occurred. After committing the complete v0.5 implementation, freeze another
small excluded Qwen confirmation and audit both the deterministic outcome and
free-text grounding before considering a broad multi-model sweep.

### Frozen v0.5 specification confirmation

The implementation was committed at `69c67ef` before the experiment was
defined. The excluded confirmation freezes the same deliberately small six-cell
shape as the two preceding specification gates: Qwen 3.8 once on each incident
under Mini and pinned Pi 0.84.4, interleaved across harnesses, with no retry or
adaptive repetition. This is not an additional capability sample and cannot
support reliability, stochasticity, harness-ranking or latency-tail claims.

The plan hash-binds the committed v0.5 protocol, cases, verifier, adapters and
offline qualifications, together with the Qwen deployment digest and Ollama
0.33.2 identity. It preserves a 300-second active-time limit, 180-second
provider timeout, no turn or token budget, a 40-read emergency safeguard, a
30-second empty-runtime/process observation before each cell and fresh Pi
Seatbelt acceptance. Runtime and model metadata were rechecked without model
load or inference.

The post-run audit is extended for the new evaluation boundary. It must verify
exact canonical scope use, local `evidence_ids` attachment semantics, response
normalization and traceability of deterministic failures. It must also review
every free-text claim for grounding and polarity. The latter is not silently
folded into the 15-check result: deterministic success and final content
acceptance remain distinct.

The resumable controller and public-safe report path pass six focused offline
tests; the plan passes four. The repository passes 419 Python and 21 active Node
tests, with one opt-in transport test skipped. No repository execution
authorization was created. A later clean-window statement must first authorize
an independent hash-bound artifact; the real resource gate still applies to
every live cell.

### v0.5 confirmation and human gate result

The later authorization was bound to the already frozen plan and explicitly
excluded a broad sweep, retries and remote push. The controller then completed
the six interleaved Qwen 3.8 cells exactly once. All runs terminated normally;
five responses were strict JSON and one intact Pi object was recovered from
surrounding text under the frozen normalizer. No timeout or runtime failure
occurred.

The official primary result is 0/6. Five schema-valid reports pass 68/75
essential checks; one otherwise coherent Pi report uses `rationale` where the
schema requires `reason`, so it fails the first and only observed schema check.
The six active-time observations range from 76.96 to 232.39 seconds with a
101.31-second median. These values remain descriptive, not a tail distribution.

Human comparison of every report, failed check and source event found no new
benchmark false negative and no blocking specification ambiguity. The misses
are visible candidate failures: incomplete local evidence attachment, omitted
causal waypoints, an unattached impact event, a missing uncertainty, one schema
field error and a missing controlled impact. Every candidate nevertheless
identified the correct root cause, trigger, scope and recovery state, so the
strict conjunction must not be paraphrased as complete diagnostic failure.

The mandatory supplemental prose review passes four of six reports. One report
incorrectly carries the initial backlog count into the last observation, while
another asserts absence of order loss and checkout impact more strongly than
the supplied excerpts support. This is positive evidence for the two-layer
design: deterministic codebooks and evidence structure remain machine-scored,
while free-text grounding and polarity remain separately judged.

The v0.5 specification gate passes. No v0.6 repair is required before the next
Capability Sweep. A broad v0.5 model matrix may be prepared, but it requires a
separate frozen plan and later execution authorization. The present n=1 cells
remain excluded from reliability, stochasticity, tail-latency and causal
harness-ranking claims.

### Frozen five-model v0.5 Capability Sweep

The next measured plan is now frozen after the controller implementation was
committed at `2f7110e`. It selects exactly the five ordered `active_default`
deployments from the lifecycle registry: Qwen 3.6, Qwen 3.8, Muse Glimmer,
Ornith 1.5 and Gemma 4. Nemotron remains specialist opt-in, Granite remains
diagnostic-only and GPT-OSS remains retired from the active cohort.

Each deployment receives all three incidents under both Mini v0.5 and pinned
Pi 0.84.4, producing 30 unique cells. The order inherits the balanced
pre-output v0.2 design, now with v0.5 harness identities: no consecutive model,
15 cells per harness, ten per case and model position sums within two. Neither
the excluded v0.5 confirmation nor any v0.2 result is counted as a cell.

The study keeps one run per configuration, no automatic retry and no adaptive
repetition. It can map observed capability but cannot estimate success
probabilities, quality stochasticity or latency tails. Mini and Pi remain
complete systems, and their outcome difference cannot be attributed to one
isolated harness feature. Deterministic semantic success and strict transport
will be reported separately; every candidate report will later receive the
same supplemental source-grounding and polarity audit used at the v0.5 gate.

Seven generic controller/report tests and four exact frozen-plan tests pass
without model contact. The plan explicitly records
`live_execution_authorized=false`. A later post-freeze clean-window statement
must be encoded against the exact plan hash before the durable controller may
create its first run. Every actual cell still faces the 30-second empty-runtime
and blocking-process gate.

### Measured v0.5 Capability Sweep result

The post-freeze authorization was recorded separately and the controller then
completed all 30 cells once, without retry. All per-cell resource gates passed.
Twenty-seven cells returned a parseable report; two Glimmer/Pi cells and one
Ornith/Pi cell reached the 300-second active-time boundary without one. Strict
transport is 22/30 and deterministic semantic success is 1/30.

The strict result is diagnostically useful because the component outcomes are
retained. All 27 reports passed root cause, trigger, affected scope and citation
integrity. The dominant failures are causal-chain completeness (18 cells),
critical evidence role-linking (15) and rejected-hypothesis evidence (13).
Qwen 3.6 with Pi produced the sole exact semantic success; Qwen 3.8 delivered
the strongest consistent component coverage with 6/6 runtime and strict
transport completion and 80/90 checks across its cells.

The required supplemental review accepts the free text of 24/27 reports. One
report carries an initial backlog count forward after the final evidence has
reduced it, one confuses a single request duration with p95 latency and one
turns absence of evidence into categorical absence. The latter distinction
demonstrates why free-text polarity remains outside the deterministic codebook.
No new verifier defect was found, and the sole deterministic success also
passes this layer.

These results do not authorize a broad reliability claim. Every exact
system-case configuration still has n=1. Any next repetition study must be a
separately frozen subset with its own question; the capability sweep must not
be retroactively expanded.

## Deferred artifact workflows

These families remain deliberately out of the immediate implementation scope.
Their order is frozen as a planning preference, not as an experiment design.

The first cross-format read-only decision case now has a tested semantic
contract and source blueprint, but no binary artifacts or qualified harness.
Its [v0.1 design](multi-format-document-analysis-v0.1.md) admits XLSX, DOCX and
PDF extraction one family at a time before they may appear together in a
measured run. Spreadsheet repair, Word assembly and PDF/OCR below remain
distinct manipulation tasks; the design-stage analysis case does not complete
or supersede them.

### 2. Spreadsheet Repair and Reporting

Use real `.xlsx` and CSV artifacts with deterministic checks for values,
formulas, sheet structure, protected cells, formatting and external links.
Recalculation/runtime identity must be frozen separately from model identity.

### 3. Word Report Assembly

Use multiple sources plus an existing `.docx` template. Verify semantic
content, package structure, styles and tables, then render for visual layout
checks. Never use byte equality as the primary correctness criterion.

### 4. PDF and OCR

Separate PDF extraction, form filling and report generation from arbitrary PDF
editing. Split vision-native OCR from a common-OCR-tool-plus-LLM pipeline;
these answer different system questions and must not share one leaderboard.

## Cross-format guardrail

For every later binary-document task, keep two questions separable where they
matter:

1. can the model reason over a canonical extracted representation; and
2. can the complete agent system manipulate the real artifact correctly?

Document libraries, office/runtime versions, rendering tools and file-format
capabilities belong to the experimental identity. Add only one new artifact
family at a time.
