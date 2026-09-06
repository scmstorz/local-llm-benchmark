# Clock Skew and Partial Recovery

This synthetic Track B development case tests chronology reconstruction when a
single payment node writes timestamps 7 minutes 42 seconds ahead of UTC. Edge
receive times, trace IDs and an independent clock observation establish the
real order; naïvely sorting all timestamps produces the wrong trajectory.

Removing the node restores new checkout authorizations, but a reconciliation
backlog remains at the last observation. The correct outcome is therefore
partial recovery. Provider rate limits and database-replica lag are plausible
but evidenced counter-hypotheses.

This case uses report contract and verifier v2. It is offline-qualified input,
not a live model result or a reliability sample.

```bash
python3 -m local_llm_benchmark.log_incident_v02 verify-reference \
  --case tasks/agentic/log-incident-analysis/clock-skew-partial-recovery/case.json
```
