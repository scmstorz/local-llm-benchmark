# Coding Track B

Track B evaluates the same coding tasks inside agent systems. It changes the
harness from Track A while keeping the task fixture and strongest available
deterministic verifier fixed.

Two harness families are developed and reported separately:

1. `mini-v0.3`, a project-owned time-first loop with a schema-constrained JSON
   action protocol;
2. `pi-v0.3`, the external Pi coding agent pinned to one exact package and
   qualified with time as its primary capability budget.

`mini-v0.2` and `pi-v0.2` remain immutable historical harnesses. Their adapters,
protocols and results are not rewritten by v0.3.

OpenCode is a third candidate, not a third qualified family. Its
[`v0.1 qualification card`](opencode-qualification-card-v0.1.json) pins the
candidate package metadata and defines five gates: package/CLI locking,
isolated no-inference configuration, event and hidden-model-call attribution,
executable sandbox acceptance, and only then one preregistered excluded smoke.
Until those gates pass, OpenCode must not be added to `track-b-v0.2.json` or to
any measured comparison.

The v0.1 harnesses remain available only for reproducing their historical
development smokes.

The two families are not interchangeable repetitions. Their prompts, tool
implementations, context policies and failure behavior differ, so every result
must retain its harness identity.

## Qualified v0.3 task subset

Pi v0.3 and Mini v0.3 use three cases selected from the Track A cross-case
report:

- `php-payment-result-migration` tests whether direct file-writing tools remove
  the strict multi-file response-envelope floor while retaining all 12 tests;
- `async-cache-coalescing` tests whether iterative public-test feedback can
  repair a genuine asynchronous invalidation failure that no Track A deployment
  solved;
- `pagination-cycle-guard` adds a Python standard-library bug fix with exact
  fetch-boundary behavior and the corrected v1.2 hidden cycle verifier.

## Shared experimental boundary

- The agent may read only candidate-visible fixture files.
- The agent may modify only paths allowed by the Track A artifact contract.
- Hidden tests and hidden-test paths are never exposed during the trajectory.
- Public tests may be requested up to the frozen per-run limit.
- Browser and external network tools are unavailable.
- The model provider endpoint must be an HTTP loopback origin; a remote
  OpenAI-compatible endpoint is rejected before run creation.
- A harness-level rerun is a new benchmark run, not another agent step.
- Final verification runs once after the trajectory and remains separate from
  tool feedback.
- Runtime completion, verifier success and valid agent termination are stored
  separately.
- Agent turns are recorded but are not a normal success limit. Their semantics
  differ across harnesses and they are trajectory evidence, not a shared unit
  of capability.
- The 900-second budget covers active harness work. Deliberate pauses between
  the split mini-harness CLI commands do not consume that budget.

The historical shared protocol in [`track-b-v0.2.json`](track-b-v0.2.json) is frozen for
single-attempt Capability Sweeps. Both adapters, their repository tests and
their no-inference machinery checks were complete before the freeze. This does
not turn one run per configuration into reliability evidence.

The first real-model harness checks are preregistered in
[`php-ornith-development-smokes-v0.1.json`](php-ornith-development-smokes-v0.1.json).
They are one excluded development smoke per harness, not measured repetitions
and not evidence for a harness ranking.

Both PHP smokes are complete. Mini-v0.1 stopped after three fenced-JSON
protocol errors without invoking a tool. Pi-v0.1 produced code that passed all
4 public and 8 hidden checks, but its successful public test consumed working
turn 12 and the policy aborted the following settling turn. Its verifier passed
while its agent termination and overall verified outcome failed. The layered
result is recorded in the
[`development-smoke report`](../../../reports/coding/track-b-php-development-smokes-v0.1.md).

The observed attempts remain unchanged. The first proposed response was a
separate termination-only turn. Methodology review rejected that approach:
v0.2 has no normal turn limit and instead relies on wall time, total output
tokens, tool-specific operation budgets and Mini's protocol-error limit.

The next excluded machinery check is frozen in
[`async-cache-qwen38-development-smokes-v0.2.json`](async-cache-qwen38-development-smokes-v0.2.json).
It runs `qwen3.8:27b-mlx` once under Mini v0.2 and once under Pi v0.2 on the
JavaScript async-cache case. It is not a measured comparison and permits no
retry or repair. Both attempts are complete and recorded in the
[`v0.2 development-smoke report`](../../../reports/coding/track-b-async-cache-development-smokes-v0.2.md).

Mini read, edited and reached green public tests, but Qwen added leading prose
to three JSON actions despite receiving the schema. The third strict protocol
error ended the trajectory, and final verification passed only 6/8 hidden
checks. Pi completed normally after one failed and one successful public-test
run; final verification passed all 4 public and 8 hidden checks. These single
excluded attempts demonstrate a harness-sensitive outcome but cannot rank the
harnesses or estimate reliability.

## Mini-harness action protocol

Each model turn returns exactly one JSON object. Mini-v0.2 passes the versioned
[`action schema`](schemas/mini-action-v0.2.json) directly to Ollama's `format`
field. The parser remains strict and performs no post-generation fence repair.
The available actions are:

- `read_file`
- `write_file`
- `replace_text`
- `run_public_tests`
- `finish`

Invalid JSON or an invalid action becomes a recorded protocol error and is fed
back to the model. The controller never repairs a malformed action silently.
Turns, including protocol-error turns, remain recorded trajectory metrics.

Mini v0.3 retains the same strict five-action surface in a newly versioned
schema and prompt. It removes total-token and protocol-error termination from
the normal capability boundary, accumulates only active model and tool time,
and records final deterministic-verification time separately. Its
[`qualification record`](mini-v0.3-qualification.json) freezes the no-inference
evidence and implementation hashes. The first separately frozen
[`Qwen 3.8 JavaScript smoke`](mini-qwen38-js-development-smoke-v0.3.json) made
no live request: its resource gate was red, and a later pre-execution audit
changed the adapter hash by adding durable request checkpointing. It is
preserved as superseded evidence. The revised
[`v0.3.1 smoke plan`](mini-qwen38-js-development-smoke-v0.3.1.json) freezes the
post-audit commit and current hashes. Its one excluded run is complete: Qwen
used six valid turns, passed 4/4 public tests and 6/8 hidden checks, then failed
as `hidden_tests_failed` on in-flight invalidation. The machinery gate passes
because this is a complete task-level failure with no adapter defect. See the
[`public smoke report`](../../../reports/coding/track-b-mini-qwen38-js-development-smoke-v0.3.1.md).
The measured cohort was frozen separately and did not reuse the smoke result.

That cohort is frozen in
[`mini-capability-sweep-v0.3.json`](mini-capability-sweep-v0.3.json). It applies
the same five deployments, three tasks and cell order as the completed Pi v0.3
screen. Every cell is a fresh one-run observation; there are no automatic
retries and no reliability or tail-performance claims.

The Mini cohort completed all 15 cells with 6 verified successes: PHP 4/5,
JavaScript 0/5 and Python 2/5. Qwen 3.6 covered two of the three cases; each
other deployment covered one. The nine failures include six hidden-test
failures, two active-time expirations and one emergency public-test safeguard.
The [public Mini report](../../../reports/coding/track-b-mini-capability-sweep-v0.3.md)
keeps all per-cell outcomes and trajectory metrics visible.

Both public reports can be regenerated without contacting a model:

```bash
python3 -m local_llm_benchmark.mini_v03_report \
  --sweep-dir results/agentic-sweeps/mini-v03-sweep-20260904T213634Z-a652de35

python3 -m local_llm_benchmark.track_b_system_report
```

The split v0.3 command surface is:

```bash
python3 -m local_llm_benchmark.mini_v03_adapter start --model MODEL --case CASE
python3 -m local_llm_benchmark.mini_v03_adapter call --run-dir RUN_DIR
python3 -m local_llm_benchmark.mini_v03_adapter step --run-dir RUN_DIR
python3 -m local_llm_benchmark.mini_v03_adapter finalize --run-dir RUN_DIR
```

For a measured cohort, the stepwise controller keeps Ollama-only model calls
separate from sandboxed action and verifier execution:

```bash
python3 -m local_llm_benchmark.mini_v03_sweep start
python3 -m local_llm_benchmark.mini_v03_sweep model-call --sweep-dir SWEEP_DIR
python3 -m local_llm_benchmark.mini_v03_sweep advance --sweep-dir SWEEP_DIR
python3 -m local_llm_benchmark.mini_v03_sweep cleanup --sweep-dir SWEEP_DIR
```

`call` contacts Ollama but never executes candidate code. `step` may run only
the frozen public test, and `finalize` runs the public and hidden verifier; the
latter two commands therefore require the surrounding Codex execution sandbox
or another explicit sandbox. Pi and Mini retain different prompts, tool
implementations, context accumulation and error behavior. Their completed
[paired report](../../../reports/coding/track-b-pi-vs-mini-system-comparison-v0.3.md)
is therefore a comparison of two complete systems rather than a one-factor
causal ablation. Pi reached 9/15 verified outcomes and Mini 6/15; they agreed
on the binary outcome in 10/15 matched cells. With `n=1` per system cell, these
differences guide later targeted repetitions but do not estimate reliability.

## Targeted system replication

The first follow-up is frozen in
[`targeted-system-replication-v0.1.json`](targeted-system-replication-v0.1.json).
It was designed after the paired screen but before any fresh requests. It
selects two opposite disagreement cells and adds exactly two fresh attempts to
each Pi and Mini system cell, with no retries or adaptive repetitions.

All eight fresh attempts completed. Including the separately identified
baseline, the descriptive outcome sequences are:

| Model and case | Pi v0.3 | Mini v0.3 |
| --- | --- | --- |
| Qwen 3.8 / JavaScript async cache | pass, fail, pass | fail, fail, fail |
| Qwen 3.6 / Python pagination guard | fail, fail, fail | pass, pass, pass |

This small outcome-selected sample does not estimate success probability or
latency tails. It does establish that the original comparison was not explained
by one uniformly superior harness: the two cross-system differences point in
opposite directions, and Pi/Qwen 3.8 itself varies across attempts. See the
[public replication report](../../../reports/coding/track-b-targeted-system-replication-v0.1.md)
for per-run outcomes, trajectory counts, duration ranges, provenance and
limitations.

The mixed controller is resumable across both harness families:

```bash
python3 -m local_llm_benchmark.track_b_replication start
python3 -m local_llm_benchmark.track_b_replication live --study-dir STUDY_DIR
python3 -m local_llm_benchmark.track_b_replication advance --study-dir STUDY_DIR
python3 -m local_llm_benchmark.track_b_replication cleanup --study-dir STUDY_DIR
```

The public report can be regenerated from retained local evidence without a
model request:

```bash
python3 -m local_llm_benchmark.track_b_replication_report \
  --study-dir results/agentic-studies/track-b-replication-20260905T065124Z-cbc09fb5
```

## Pinned Pi boundary

The adapters target
`@earendil-works/pi-coding-agent@0.84.4`, whose exact npm integrity is recorded
in both [`pi-v0.2.json`](pi-v0.2.json) and
[`pi-v0.3.json`](pi-v0.3.json). Pi runs non-interactively in JSON event mode,
without sessions, context files, skills, discovered extensions, themes or
startup network operations. Only the explicitly supplied benchmark-policy
extension is loaded.

Pi's `read`, `write`, `edit` and `bash` tools remain Pi implementations, but the
extension applies the benchmark path policy and allows `bash` only for the one
frozen public-test command. The controller performs hidden verification after
Pi exits.

The v0.3 macOS pilot wraps Pi and all descendants in
`pi-macos-seatbelt-v0.2`. A run-specific deny-by-default profile is accepted
only after twelve executable no-inference boundary checks pass. The profile blocks
the rest of the user's home and repository, rejects symlink escapes and
external networking, restricts executable paths, permits only exact declared
writes plus Pi's isolated run-local state and temporary files, and allows
network access solely to local Ollama. Wall time, CPU time, file size and open
file descriptors are bounded; timeout cleanup targets the whole Pi process
group.

The twelfth check starts the exact task-specific runtime without running test
code. PHP resolves to a direct interpreter rather than the machine's selection
wrapper. Homebrew Python receives the additional fixed `Python.app` child
executable required by its launcher. Node, PHP and Python each passed the full
boundary suite.

Live trajectory execution and final verification are deliberately separate.
The Pi command cannot read the hidden verifier. After Pi exits, the controller
hash-checks its raw artifacts and a second command runs public plus hidden
verification without model access. That verifier command still executes
candidate-authored code and therefore runs inside the surrounding Codex sandbox
or another explicit verifier sandbox.

Primary sources consulted for the adapter:

- [Pi repository and CLI documentation](https://github.com/earendil-works/pi/tree/main/packages/coding-agent)
- [Ollama's Pi integration documentation](https://docs.ollama.com/integrations/pi)
- [Ollama structured outputs](https://docs.ollama.com/capabilities/structured-outputs)
- [Pinned npm package metadata](https://www.npmjs.com/package/@earendil-works/pi-coding-agent/v/0.84.4)

## First measured Pi capability sweep

The frozen [`pi-capability-sweep-v0.1.json`](pi-capability-sweep-v0.1.json)
crosses all eight deployments cataloged on 2026-09-03 with both pilot tasks.
The PHP block uses catalog order and the JavaScript block reverses it, balancing
every model's early-versus-late placement. Earlier development smokes are not
reused. Each configuration receives one fresh attempt, so this is a capability
screen rather than a reliability or performance-distribution study.

The controller runs the exact-model and 30-second empty-Ollama gate immediately
before every live Pi trajectory, unloads the deployment afterwards and
checkpoints preparation, sandbox acceptance, execution and final verification:

```bash
python3 -m local_llm_benchmark coding-agent-pi-sweep
```

After an external interruption or resource-gate pause, resume the existing
sweep without repeating terminal outcomes:

```bash
python3 -m local_llm_benchmark coding-agent-pi-sweep-resume \
  --sweep-dir results/agentic-sweeps/PI-SWEEP-ID
```

After completion, build the public-safe derived report with the separate
post-run module. It is intentionally outside the CLI artifact frozen into the
measured plan:

```bash
python3 -m local_llm_benchmark.pi_report \
  --sweep-dir results/agentic-sweeps/PI-SWEEP-ID \
  --json-output reports/coding/track-b-pi-capability-sweep-v0.2.json \
  --markdown-output reports/coding/track-b-pi-capability-sweep-v0.2.md
```

The first plan was interrupted by a computer crash after its eight PHP units.
Because Ollama changed from 0.32.15 to 0.33.2, the partial cohort was closed
rather than resumed across runtime identities. Its completed terminal units
are preserved in the
[`interrupted-cohort report`](../../../reports/coding/track-b-pi-capability-sweep-v0.1-interrupted.md).

A replacement plan froze the new runtime identity and restarted the full
Cartesian cohort. It completed all sixteen units. The primary outcome was 6/16
verified successes, all on PHP. Among the ten non-successes, five were
conclusive budget failures, one was a conclusive hidden-test failure and four
were inconclusive transport or standby outcomes. The detailed
[`v0.2 report`](../../../reports/coding/track-b-pi-capability-sweep-v0.2.md)
includes checks, active time, turns and tool calls for every observation.

Post-run review identified two implementation mismatches. Pi v0.2 did not
explicitly receive the recorded 300-second provider timeout, and the policy
extension's `Date.now()` wall-time check counted notebook standby even though
the parent process used monotonic active time. Review also found a design
mismatch: a hard 12,000-token trajectory ceiling can terminate a model while
the user-relevant time budget remains.

The frozen v0.2 adapter and raw runs remain unchanged. Qualified
[`track-b-v0.3.json`](track-b-v0.3.json) makes 900 seconds of active parent time
the primary capability limit. The 300-second provider timeout remains explicit;
turns and total tokens become measurement-only. Path restrictions remain hard,
while file-operation and public-test counts become generous emergency loop
safeguards. The versioned
[`Pi v0.3 harness`](pi-v0.3.json), configuration builder, policy extension,
live adapter and language-aware Seatbelt profile implement these semantics.
All three cases passed no-inference preparation and twelve real Seatbelt checks.
The pinned Pi runtime also terminated against a deliberately stalled local stub
under a short qualification timeout, proving the configured provider deadline
is active without contacting Ollama or a model. The public-safe
[`qualification record`](pi-v0.3-qualification.json) freezes the evidence and
implementation hashes without exposing local paths.

New v0.3 runs use the separate versioned command surface; the historical main
CLI continues to reproduce v0.2:

```bash
python3 -m local_llm_benchmark.pi_v03_adapter prepare \
  --model qwen3.6:35b-a3b-mxfp8 \
  --case tasks/coding/dev/pagination-cycle-guard/case-whole-file-v1.2.json

python3 -m local_llm_benchmark.pi_v03_adapter sandbox-check \
  --run-dir results/agentic-runs/pi-v03-agentic-run-ID
```

The separately frozen
[`pi-capability-sweep-v0.3`](pi-capability-sweep-v0.3.json) plan selected the
five `active_default` deployments and all three cases. It completed all 15
units after the resource gate passed, producing 9 verified successful outcomes.
The public [cross-case report](../../../reports/coding/track-b-pi-capability-sweep-v0.3.md)
keeps runtime, agent termination, deterministic verification and final verified
success separate. The result is a single-run capability screen, not reliability
or performance-distribution evidence.

The public-safe JSON and Markdown reports can be regenerated from the retained
local raw sweep without running a model:

```bash
python3 -m local_llm_benchmark.pi_v03_report \
  --sweep-dir results/agentic-sweeps/pi-v03-sweep-20260904T154510Z-eb3b2311
```
