# Agentic Log Incident v0.5 Specification Audit

The v0.5 confirmation completed all six planned cells and passed its actual
methodological gate: manual review found **no new verifier false negative and no
blocking specification ambiguity**. Its frozen official outcome remains **0/6
deterministic semantic successes**. That zero is strict but traceable: every
report identified the central incident mechanism, while every report also
missed at least one explicit structured requirement or the report schema.

## Official outcomes

| Position | System | Case | Runtime | Strict JSON | Official result | Checks | Active time |
| ---: | --- | --- | --- | --- | --- | ---: | ---: |
| 1 | Mini | Checkout pool regression | complete | yes | task failure | 14/15 | 76.96 s |
| 2 | Pi 0.84.4 | Retry queue amplification | complete | yes | task failure | 14/15 | 128.19 s |
| 3 | Mini | Clock skew partial recovery | complete | yes | task failure | 13/15 | 82.27 s |
| 4 | Pi 0.84.4 | Checkout pool regression | complete | yes | schema failure | 0/1 | 120.36 s |
| 5 | Mini | Retry queue amplification | complete | yes | task failure | 14/15 | 80.31 s |
| 6 | Pi 0.84.4 | Clock skew partial recovery | complete | no; normalized | task failure | 13/15 | 232.39 s |

All six cells completed technically with valid agent termination, and no retry,
timeout or runtime failure occurred. Five responses were bare JSON. The frozen
normalizer recovered one intact object from the remaining Pi response without
repairing its contents. Five schema-valid reports passed 68 of 75 applicable
checks; the sixth stopped after failing the schema check, so the aggregate
observed count is 68/76 rather than an artificial 68/90.

## What the zero does and does not mean

Manual inspection found the correct root cause, trigger, incident scope and
recovery state in all six candidate reports. The official primary outcome is a
conjunction, however: one missing required chain event, one incomplete local
evidence attachment or one invalid schema field makes a report an unsuccessful
verified outcome. It therefore does not mean that Qwen failed to diagnose every
incident; it means that none of the six complete systems produced a report that
satisfied the whole frozen contract in this one attempt.

The individual misses are concrete:

- Position 1 attached only `AUTH-502` to the authentication rejection. The
  reason mentioned other useful events, but v0.5 explicitly says that only the
  entry's `evidence_ids` count.
- Position 2 omitted the zero-delay retry event and the intermediate
  queue-draining waypoint from its structured causal chain.
- Position 3 named the initial backlog event in prose but did not attach it
  under the impact evidence role, and omitted the required payment-data-loss
  uncertainty.
- Position 4 used `rationale` instead of the schema's required `reason` field
  for uncertainties. The response was strict JSON, illustrating that transport
  compliance and schema validity are different properties.
- Position 5 omitted the zero-delay retry event from its structured causal
  chain.
- Position 6 omitted the intermittent-rejection event from the chain and the
  required latency impact code. Its surrounding response text independently
  caused strict-transport noncompliance.

These are candidate-attributable misses under visible rules. No failed check
required reinterpretation, fuzzy matching or a hidden representation choice.

## Supplemental free-text grounding review

The separate human claim review passed four of six reports. This is not a
rescore and cannot turn a deterministic failure into success.

- Position 3 says in its diagnosis that 913 pending authorizations remained at
  the last observation. The cited recovery event records 612 remaining; the
  report's own impact section states the correct distinction between 913
  created and 612 remaining.
- Position 5 categorically says that no orders were lost and checkout was not
  affected. The excerpts do not show either positive impact, but they also do
  not establish those stronger absence claims. The grounded formulation would
  be that the supplied evidence does not establish order loss or checkout
  unavailability.

The other four reports keep their free-text claims grounded and correctly
polarized. This confirms why v0.5 removed substring-based prose scoring: the
controlled codes are deterministic, while factual nuance such as "not
observed" versus "did not happen" belongs in a distinct judgment layer.

## Decision

The v0.5 specification gate passes. The official 0/6 result and all raw run
records remain unchanged, but the evaluator no longer shows a blocking
alignment defect. A broad v0.5 multi-model Capability Sweep may now be prepared
as a separately frozen experiment. This audit does not authorize its execution.

The present evidence still has one observation per system/case cell. It cannot
support reliability, stochasticity, latency-tail or one-factor harness claims;
Mini and Pi remain different complete-system conditions. Durations are
descriptive only.
