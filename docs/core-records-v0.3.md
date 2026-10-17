# Core coverage records 0.3

The native direct-coding runner records completion as
`execution.execution_status = completed`, with separate immediate verification
and completion timestamps. It does not write the generic top-level `status`
field used by text runs or `state` used by agent adapters. Coverage 0.2 can
therefore label a completed direct-coding result as still in progress.

The additive 0.3 reader recognizes that native completion shape:

```bash
python3 -m local_llm_benchmark.core_records_v03 \
  --plan results/core-suites/COMPARISON/execution/plan.json \
  --admission-study results/core-suites/COMPARISON/study.json
```

It builds on [coverage 0.2](core-records-v0.2.md), retaining its native identity
checks and exact-plan external Pi admission. Only an identity-checked
`direct-coding` row currently marked `in_progress` is eligible. Recognition
requires Track A, a known native direct-coding harness, completed execution,
immediate verification with a completion timestamp, a Boolean verified outcome,
and timezone-aware execution/verification timestamps after the run start. Native
record construction assigns the two completion timestamps separately; their
relative order does not establish a separate lifecycle transition.

Missing or deferred verification, incomplete execution, unknown harnesses,
contradictory identity and changed bound sources are never promoted. A completed
failed answer remains a failed answer. Original readers, run records, scores,
task definitions and harnesses are unchanged. This command reads files only;
it does not contact Ollama, retry inference or rescore a response.
