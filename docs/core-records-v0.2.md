# Core coverage records 0.2

The frozen coverage 0.1 reader expected every completed run to contain native
model/runtime observations in `deployment`. Mini has those fields; frozen Pi
supplier runs record only the requested model there. Their exact artifact and
runtime are checked by the controller's fresh pre-inference resource gate.
The excluded [Ollama 0.40.5 readiness pair](../reports/agentic/core-runtime-readiness-v0.1.md)
exposed this record-shape difference during real integration.

The additive `core_records` reader distinguishes **identity unrecorded** from
**identity mismatch**, and can validate the separate admission evidence:

```bash
python3 -m local_llm_benchmark.core_records \
  --plan results/core-suites/COMPARISON/execution/plan.json \
  --admission-study results/core-suites/COMPARISON/study.json
```

The task catalog, generated commands and original coverage reader stay at their
frozen versions. This new command reads existing files without modifying a
run, verifier result or prior coverage report. It contacts no model endpoint.

The optional admission study must bind the exact plan SHA-256. A matching unit
must identify the exact run directory and final run-record hash. Its
`resource_evidence` must show a passing zero-inference gate with the expected
model name, full digest and Ollama version. Observation and gate-completion
timestamps must fall after plan creation and before that run's inference start.
Case, harness and evaluation configuration must agree, and bound source inputs
must have no drift. The coverage output labels the evidence basis and retains
the admission source's path and hash.

Without adequate evidence, missing native identity stays `identity_unrecorded`.
A contradictory native observation remains `identity_mismatch`; an external
gate cannot override it. This validates configured deployment at preflight; it
does not fabricate a missing native observation or HTTP request counter.

A `complete` cell still means a recorded execution, including an observed task
failure. Deterministic correctness, strict transport, source-grounded prose and
performance remain separate. The background-download readiness attempts stay
excluded from measured comparisons regardless of their coverage status.
