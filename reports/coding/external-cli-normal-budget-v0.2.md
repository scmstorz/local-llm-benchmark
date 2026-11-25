# Mirror and Mistral Vibe: normal-budget JavaScript checks v0.2

Both systems produced code that passes the unchanged public, hidden and integrity
checks. Vibe completed the overall run in 727.1 seconds. Mirror reached the
900-second parent deadline after producing passing code, so its overall result
remains a timeout. These are two excluded development checks, not measured core
coverage or a general harness ranking.

| Observation | Mirror CLI | Mistral Vibe |
| --- | --- | --- |
| Pinned package | reflection-mirror 0.1.0 | mistral-vibe 2.26.1, Python legacy |
| Parent budget | 900 s | 900 s |
| Wall time including cleanup | 900.5 s, timeout | 727.1 s, completed |
| First confirmed native source edit | 604.7 s | 608.4 s |
| Public / hidden / integrity checks | All pass | All pass |
| Overall verified success | No: parent timeout | Yes |
| Completion requests / completed responses | 15 / 14 | 7 / 7 |
| Known completion-token subtotal | 20,747; last response unknown | 20,260; all responses known |
| Native context compactions | 1 | 1 |
| Denied native tool outputs | 4 | 0 |

Each system ran exactly once on `coding.dev.async-cache-coalescing`, using the
same Qwen 3.8 deployment and Ollama 0.40.5 as the initial checks. Each had its own
fresh 30-second empty-state gate and disposable workspace. Both changed only
`src/async-cache.mjs`, improved the public baseline from 3/4 to 4/4, and passed
the separate hidden verifier. Process cleanup and empty postflights passed.
No other consumer was stopped and no attempt was retried.

Compared with the [initial 120-second checks](external-cli-qualification-v0.1.md),
both prompts explicitly declare the workspace and Mirror's configured response
ceiling rises from 3,000 to 8,192 tokens. Vibe starts in the correct workspace
without the earlier denied parent-directory probes. Both need about ten minutes
before their first confirmed edit. The short budget was insufficient for these
observed trajectories, but several settings changed together: this does not
establish that increasing time alone would have solved the original attempts.

The wire evidence explains much of the time cost. A single Vibe response takes
559.7 seconds and uses 17,824 completion tokens, including streamed reasoning.
Both systems return reasoning text despite their native `none`/`off` declarations;
neither transmits an explicit `think` or `reasoning_effort` constraint. Those
declarations therefore do not establish backend thinking-off behavior. Output
token totals include all response content; no exact reasoning-token split is
available. Prompt-token sums in the JSON include repeated and cached context.

Mirror's native context management also lowers the configured response ceiling
as context grows: one response ends with `length` at `max_tokens=5508`, followed
by a 141.7-second context summary. That summary request has no explicit output
ceiling. After implementing and publicly testing the passing code, Mirror tries
two scratch-file writes and two shell alternatives; all four are denied by the
existing write boundary. It continues working until timeout. These observations
identify configuration, context and tool-policy interactions as further work;
they do not isolate a single cause of its failure to finish.

Before inference, 697 regression tests pass with four expected opt-in skips;
21 targeted tests include both updated native JavaScript tool checks and both
deadline checks, with 62 OS probes and 18 synthetic requests. All 411 earlier
source fingerprints, the original v0.1 report and the 23-case inventory remain
unchanged. Source freeze: `eddadd560737b3c761a56ff61056d1ab73bf6156`.

First-edit times use native successful tool-result timestamps checked against
the final source bytes. They are not exact first-byte timings. The originally
planned provider-response/request bracket can overlap by milliseconds because
the recorder and client run concurrently; native tool records provide the
reported observation instead.

Mirror's deadline shutdown exposed a recorder edge case: `IncompleteRead` left
the last journal status at `started`, with a finish timestamp and preserved
partial bytes. Its usage remains unknown. A subsequent offline correction
records that condition as a transport failure and avoids appending a second HTTP
response to an already-started stream. Twenty targeted tests and the final
698-test regression pass, with four expected opt-in skips. All 111 original
bound source files are also checked against their committed pre-inference
bytes, and the frozen raw evidence still matches after the correction. Original
receipts remain unchanged; no model run was repeated after the correction.

Next, qualify effective backend thinking control and a declared bounded scratch
testing/termination policy before expanding tasks or claiming a measured
comparison. See the [v0.2 method](../../integrations/external-cli-v0.2.md) and
[machine-readable observations](external-cli-normal-budget-v0.2.json).
Raw wire, native state, code and authorization evidence remain local.
