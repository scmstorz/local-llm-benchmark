# Coding Track B PHP development smokes v0.1

The same Ornith deployment failed under both frozen overall outcome contracts,
but for fundamentally different reasons. The mini-harness never crossed its
strict JSON transport boundary. Pi produced code that passed all twelve
deterministic checks, but it reached that state in the final permitted working
turn and had no remaining turn in which to terminate normally.

These are excluded development smokes. They validate and diagnose the harnesses;
they do not rank them or estimate reliability.

## Frozen scope

| Dimension | Value |
| --- | --- |
| Case | `coding.dev.php-payment-result-migration` v1.0.0 |
| Language / family | PHP / API migration |
| Deployment | `ornith-1.5:35b` |
| Deployment digest | `9f3b89b2521908dd2e6f7a11fa368e62c8f89e1075f22604e4d1a76dd1240fcc` |
| Harness order | mini-v0.1, then pi-v0.1 |
| Attempts | one cold attempt per harness |
| Retries or repair | none |
| Context | 16,384 tokens |
| Turn output ceiling | 1,600 tokens |
| Total output ceiling | 12,000 tokens |
| Working-turn ceiling | 12 |

The plan was frozen before either result. Both attempts remain excluded from
future measured Track B aggregates.

## Layered outcomes

| Harness | Runtime | Agent termination | Final verifier | Overall verified success |
| --- | --- | --- | --- | --- |
| mini-v0.1 | success | invalid: protocol-error limit | fail: unchanged baseline | false |
| pi-v0.1 | success | invalid: turn-budget abort | pass: 12/12 | false |

The final column is the frozen primary outcome. The verifier column is retained
separately because it answers a different question: whether the final code in
the disposable workspace satisfies the task's deterministic checks.

## Mini-v0.1

Run `agentic-run-20260902T130507Z-3fce1a9c` completed three Ollama requests.
Each response contained the intended JSON action inside a Markdown code fence.
The strict parser deliberately performs no fence stripping or other repair, so
all three turns became protocol errors. It stopped at the frozen limit before
any read, write, test or other tool action.

The separate final verifier then tested the unchanged fixture. It passed the
baseline's two already-green public checks and three hidden checks, but the
required layers failed overall.

| Metric | Observation |
| --- | ---: |
| Active wall time | 11.65 s |
| Model turns | 3 |
| Protocol errors | 3 |
| Tool calls | 0 |
| File writes | 0 |
| Public-test runs during trajectory | 0 |
| Input tokens | 2,877 |
| Output tokens | 66 |
| Final checks | 2/4 public, 3/8 hidden |

This is a wire-protocol fit failure. It does not show that Ornith lacks the
PHP capability needed by the task, because the model never received file or
test feedback and never installed a candidate.

## Pi-v0.1

Run `pi-agentic-run-20260902T130719Z-00667a46` used pinned
`@earendil-works/pi-coding-agent@0.84.4`. Before inference, the run-specific
`pi-macos-seatbelt-v0.1` profile passed all eleven executable acceptance checks.
Pi then ran inside that profile; hidden verification remained unavailable until
the process exited.

Pi explored the visible repository, changed exactly the two permitted source
files and ran the frozen public command twice. The first test run failed. After
one more edit, the second run passed at 85.02 seconds. The separate controller
then confirmed 4/4 public and 8/8 hidden checks, with no scope or integrity
violation.

| Metric | Observation |
| --- | ---: |
| Active wall time | 85.27 s |
| Productive model turns | 12 |
| Aborted terminal turn | 13 |
| Tool calls | 21 |
| Failed tool calls | 3 |
| File reads | 13 |
| File writes | 4 |
| Public-test runs | 2 |
| First successful public verification | 85.02 s |
| Input tokens | 59,541 |
| Output tokens | 5,685 |
| Final checks | 4/4 public, 8/8 hidden |

Two failed tool calls were policy blocks for shell commands other than the
exact public-test command. The third was the expected first red public test.
There were no model retries, malformed events or malformed audit records.

The passing second test occurred in working turn 12. Pi then opened turn 13 to
produce a final assistant response, where the frozen twelve-turn policy aborted
the operation. Pi emitted `stop_reason=error`, so the adapter correctly marked
the agent end invalid. The code verifier passed, but the overall outcome remains
`verified_success=false`; changing that label after seeing the result would
violate the frozen definition.

## Resource isolation

The first Pi preflight did not run because `Blog-Read-O-Matic` automatically
reloaded `nomic-embed-text-v2-moe:latest`. The user attempted repeated
`Ctrl-C`; the Streamlit process remained stuck with a defunct child. With
explicit approval, a targeted `SIGTERM` was attempted and had no effect. A
second explicit approval allowed `SIGKILL` against only that identified
process. The embedding model was then unloaded, and Ollama remained empty for
30 seconds before Pi started. Ornith was unloaded after completion, and Ollama
again remained empty for the full 30-second postflight.

This is not incidental bookkeeping. Without the gate, the Pi timing would have
mixed two loaded deployments and unknown memory pressure.

## What the smoke establishes

The harness changed the observed boundary. Mini-v0.1 exposed a brittle protocol
fit between Ornith and a strict project-owned state machine. Pi's native tool
interface crossed that boundary and yielded verifier-complete code. At the same
time, Pi exposed a different system-level limitation: solving the code is not
identical to completing the agent trajectory within budget.

The result therefore supports three separate statements:

1. Ornith did not complete mini-v0.1's strict action protocol in this attempt.
2. Ornith plus Pi produced a fully verifier-compliant PHP solution.
3. Ornith plus Pi did not terminate validly within the frozen twelve-turn
   trajectory contract.

None should be collapsed into a single quality score.

## Protocol consequence

The current attempts will not be rerun or repaired. Before a measured Track B
protocol is frozen, both harness families should distinguish the working-turn
budget from one termination-only settling turn. That final turn must prohibit
reads, writes, tests and every other tool, so it cannot become an unrecorded
capability-budget increase. This resolves the ambiguity revealed by the smoke
without rewriting its outcome.

The raw wall times remain descriptive only. One harness performed no useful
tool work and the other executed a full iterative repair, so this pair cannot
support a speed comparison or a harness-winner claim.

## Subsequent protocol decision

The initial report proposed twelve working turns plus one tool-free settling
turn. A later methodology review rejected that proposal. Turns are not
equivalent across harnesses: Mini emits exactly one action per turn, while Pi
may group tool calls differently. A low shared turn ceiling therefore measures
harness mechanics as much as useful capability.

Track B v0.2 removes the normal turn limit. Turns remain a recorded trajectory
metric. Wall time, total output tokens, path permissions, operation-specific
tool budgets and Mini protocol errors provide the hard run boundaries. The v0.1
smoke outcome remains unchanged and is not retroactively promoted.
