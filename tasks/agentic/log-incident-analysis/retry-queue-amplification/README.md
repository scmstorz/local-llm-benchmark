# Retry Queue Amplification

This synthetic Track B development case tests whether a read-only agent can
separate a latent retry-policy regression from the downstream slowdown that
exposes it. The incident becomes user-visible only after immediate retries
amplify queue depth and redelivery traffic.

Six mixed-format and rotated logs include exact cross-service identifiers, a
healthy message broker, and a visually salient TLS error affecting only a test
notification tenant. The candidate must reconstruct the delayed causal chain,
bound the impact, reject both distractors and identify full recovery only after
the queue drains.

This case uses report contract and verifier v2. It is offline-qualified input,
not a live model result or a reliability sample.

```bash
python3 -m local_llm_benchmark.log_incident_v02 verify-reference \
  --case tasks/agentic/log-incident-analysis/retry-queue-amplification/case.json
```
