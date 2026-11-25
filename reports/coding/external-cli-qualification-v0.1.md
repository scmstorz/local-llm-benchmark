# Mirror and Mistral Vibe integration qualification v0.1

Both pinned adapters are implemented and pass the six-cell offline coding
qualification and both native timeout probes. Real Qwen/Ollama tool exchanges
were then observed in two short development checks. Both reached their
120-second parent budget before editing a file; neither solved the task.
These checks are excluded from measured coverage and are not a harness ranking.

| System | Package | Offline tool cases | Real Qwen JavaScript check |
| --- | --- | --- | --- |
| Mirror CLI | reflection-mirror 0.1.0 | 3/3 | Parent timeout; 5 requests; no edits |
| Mistral Vibe, Python legacy | mistral-vibe 2.26.1 | 3/3 | Parent timeout; 6 requests; no edits |

The existing PHP, JavaScript and Python fixtures and final verifiers remain
unchanged. The accepted synthetic matrix has 93 OS probes plus 31 for the two
deadline preparations; all pass. Fifty synthetic completion requests exercise
42 task-tool calls and two real sleeping shell calls. Native reads, edits,
searches and actual public tests work. Hidden-test reads, protected-file edits
and controller-record reads are denied. A stub success never becomes a model
task success. The23-case inventory and existing measured registry are unchanged.

The final regression passes 693 tests with two expected
opt-in skips. The explicit native qualification passes 19 tests, including both
the six-cell tool matrix and two-deadline matrix. Complete dependency locks,
installed wheel RECORD files and exact executable hashes are checked before
execution. Hidden verification uses a byte-checked private copy after process
cleanup and evidence freeze.

The two real checks bind the installed Qwen 3.8 deployment and Ollama 0.40.5,
one fresh 30-second idle gate each, one attempt per harness and no retry. Mirror
commits three ls and four read calls; one complete response reaches its 3000-token
request ceiling. Vibe commits four shell and four read_file calls, including
two denied parent-directory probes before recovering its correct cwd. Neither
issues a file edit before timeout. Both retain the original 3/4 public checks and
fail hidden verification. Both process cleanups and empty postflights pass.

There are 11 real completion requests, nine complete responses and two interrupted
responses. Usage is known for 4/5 Mirror and 5/6 Vibe requests; token subtotals in
the JSON exclude unknown final-response usage. No paid judge API was used.

The initial checks also exposed two instrumentation issues. Mirror's observer
covered stdout notifications while missing delivered gRPC chat; the protected
wire journal still retains the tool exchange. The common delivered-message
observer is now corrected and explicitly tested for assistant/tool records.
Mirror also had about 20 seconds of transport drain after its parent deadline
(139.94 seconds including cleanup; Vibe 120.73). Waiting for response headers now
inherits the remaining parent budget. Both fixes pass fresh synthetic native
qualification and regressions. The original source-bound live receipts remain
unchanged; no real model check was repeated after the fixes.

Mirror sends max_tokens=3000; Vibe sends temperature=0; both stream. No seed or
Ollama context allocation is inferred. Native shell policies differ from Pi's
exact-public-command policy. Vibe explicitly uses its Python legacy loop; its
unified Rust harness is a different condition. With project context disabled,
Vibe's initial system prompt lacks a cwd declaration; an explicit workspace hint
should be a versioned future prompt condition. Normal capability budgets,
measured admission, log/document tools and additional cases remain separate.

See the [integration procedure](../../integrations/external-cli-v0.1.md),
[versioned contract](../../tasks/coding/track-b/external-cli-v0.1.json) and
[machine-readable report](external-cli-qualification-v0.1.json). All raw request,
response, state, source-binding and process evidence stays local.
