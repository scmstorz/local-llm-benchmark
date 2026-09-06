# Checkout Pool Regression

This synthetic Track B case tests read-only investigation across six small log
files. A deployment reduces an application-side database connection pool; a
traffic increase then exposes the capacity regression. Authentication,
inventory and database events provide plausible distractors.

The task requires UTC normalization, an ordered causal chain, exact event/file
citations, bounded impact claims, rejected hypotheses, remediation and explicit
uncertainty. The hidden reference and verifier remain outside the copied
candidate workspace.

This is a development case until a new read-only harness passes no-inference
qualification and one excluded live smoke. It is intentionally not a large-log
retrieval benchmark, a reliability study or evidence of general operations
competence.

Verify the independent reference without inference:

```bash
python3 -m local_llm_benchmark.log_incident verify-reference \
  --case tasks/agentic/log-incident-analysis/checkout-pool-regression/case.json
```
