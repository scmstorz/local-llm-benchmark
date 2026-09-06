# Log-Incident Qualification Smokes v0.2

Status: **complete with a documented protocol deviation**

These excluded development smokes test the end-to-end machinery for the common
three-case report-v2 protocol. They are not measured capability observations
and cannot support a model, speed or harness ranking.

Both systems used the same `qwen3.8:27b-mlx` deployment and the
`retry-queue-amplification` case. Each admitted run used temperature 0, seed 42,
16,384 context tokens, no normal turn or trajectory-token limit and a
300-second active-time boundary.

| Complete system | Outcome | Checks | Active seconds | Turns | Reads | Repeated reads | Input tokens | Output tokens | Failure |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- |
| `mini-log-v0.2` | fail | 11/14 | 83.52 | 7 | 6 | 0 | 14,763 | 1,853 | `deterministic_checks_failed` |
| `pi-log-v0.2` | fail | 0/1 | 170.64 | 4 | 8 | 2 | 24,702 | 7,808 | `missing_or_malformed_report` |

Mini completed a valid report but missed the exact incident start, the
canonical affected-journey identifier and one required evidence-role mapping.
It read every visible file exactly once and made no failed tool call.

Pi completed normally at the runtime level, but prefixed its JSON object with a
sentence. The strict parser correctly rejected the complete response rather
than repairing it. A diagnostic-only extraction found that the embedded JSON
would have passed 10/14 checks and still missed the incident window, canonical
scope, causal ordering and one evidence-role mapping. The official outcome
remains 0/1 because post-hoc repair is not part of the system.

Both 30-second resource gates passed. Pi additionally passed all nine real
macOS Seatbelt acceptance checks immediately before inference. Ollama was empty
after final cleanup.

## Protocol deviation

Two Mini control-layer events preceded the admitted Mini result. First, the
enclosing development sandbox denied loopback access before Ollama was reached;
that record contains zero tokens. Second, a development execution session ended
during the seventh request after six completed read turns. Its partial stream
was preserved, not reconstructed and not scored.

A fresh Mini run was then started even though the frozen plan said not to retry
an interrupted live boundary. This is explicitly recorded as a protocol
deviation. There was no automatic retry, prompt change or adaptive use of the
partial answer, but strict one-execution-attempt compliance is false. Therefore
the report is usable only as excluded machinery evidence.

## Interpretation

Both v0.2 adapters now have complete and machine-classified end-to-end outcomes.
The machinery gate is considered passed with the deviation above; verified task
success was not required. Before any measured request, the project must add and
offline-qualify a durable v0.2 sweep controller, then freeze the balanced
three-case Capability Sweep.

Candidate responses, fixture contents, hidden verifier details and absolute
local paths are intentionally absent from this public report.
