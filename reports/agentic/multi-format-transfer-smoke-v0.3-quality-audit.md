# Supplier transfer smoke v0.3 — source-grounded review

The two authorized attempts completed once each under **Ollama 0.40.2** with
Qwen `qwen3.8:27b-mlx`. Both runtime executions, terminations and strict output
transports succeeded. Both chose Atlas primary and Boreal reserve and correctly
excluded Cedar and Delta. Qwen was unloaded after each system; both postflights
were empty. No retry occurred.

| System | Frozen checks | Strict transport | Source-grounded prose |
| --- | ---: | --- | --- |
| Pi v0.4 | 11/12 | Pass | Fail |
| Mini v0.2 | 10/12 | Pass | Fail |

Pi omits the policy anchor from the dashboard conflict's own citation list,
although it cites that policy elsewhere. Mini includes every required
draft/final citation but adds a valid Atlas final-assurance row; the frozen
verifier rejects that extra citation because it requires exact sets. This is a
specification limitation, not evidence of a wrong supplier decision. Mini also
omits the required `reassess_after_new_evidence` action, despite discussing
future cutoff changes elsewhere.

Both reports misdescribe the explicitly unsigned draft as signed. Pi repeats
that error in its evidence explanation and conflict resolution. Mini repeats
it in its summary and conflict resolution while correctly calling it unsigned
in its evidence array. These are material source-grounding errors in the
central authority distinction; the correct final award does not erase them.
Minor German grammar issues are not the reason for rejection.

Pi's structured `finish_report` boundary worked in this real attempt: exactly
one schema-valid report was captured without free-text normalization. That
supports the transport part of the prediction. The full semantic-contract and
source-grounding part did not pass. No launch or sandbox failure occurred.

## Measurement limits

The inherited deterministic report leaves artifact-operation counts null
because it expects a different field name. Raw Pi tool count is 18 including
completion; Mini records 17 artifact operations and a separate finish action.
The inherited study counter also records Mini's 18 requests while treating
Pi's absent request counter as zero. **18 is not the total request count for
the pair.** Pi's exact HTTP request count remains unavailable; six recorded
agent turns are not silently substituted for that metric. Raw records and the
generated report remain unchanged.

The original Ollama-0.33.2 plan and never-executed prepared study are preserved.
This new runtime condition is not pooled with prior outcomes. One attempt per
system is excluded development evidence and supports no ranking, reliability
probability or latency distribution. The reviewer was not blinded and used no
paid judge API.

Before any measured reuse, resolve the extra-valid-citation rule and the
telemetry reporting gaps in separately versioned contracts. Neither issue
licenses a retry or retrospective alteration of these two outcomes. The
broader newcomer workflow remains deferred.
