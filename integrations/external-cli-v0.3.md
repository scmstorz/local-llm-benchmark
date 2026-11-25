# Explicit backend and scratch qualification v0.3

The opt-in [contract](../tasks/coding/track-b/external-cli-v0.3.json) selects an
explicit OpenAI-chat-to-native-Ollama text/tool bridge. The default v0.1 and
frozen v0.2 contracts and results remain unchanged. This qualifies the provider
and containment conditions; it does not admit a measured harness comparison.

Every request, including context summaries, receives native `think: false`,
temperature 0, seed 42, `num_ctx: 16384`, `keep_alive: "5m"`, and at most 1600
output tokens. Smaller CLI ceilings are honored. Mirror's native ceiling is
also 1600. Vibe's legacy backend omits an output limit, so the declared bridge
supplies it. Parent time remains 900 seconds, provider socket time 300 seconds
bounded by remaining parent time; no turn or total-token ceiling is added.

This provider adaptation is part of the complete-system condition. The private
journal retains the original CLI body, effective `/api/chat` body, raw native
NDJSON and returned client bytes. Tool arguments/results are translated with
their names, order and correlation preserved. Only the qualified text/function
subset and automatic tool choice are accepted; unsupported or conflicting
semantics fail. Streaming text, tool calls and unexpected thinking remain
visible. Native completion and usage are required. Unexpected thinking or
completion counts above the effective ceiling fail runtime conformance.

The architecture's context maximum and a CLI's declared context are distinct
from observed backend allocation. Short live qualification checks must capture
`/api/ps` after generation and report whether its observed context matches
16384. The bridge does not create a model alias or modify any deployed model.
The native API documents [thinking and runtime options](https://docs.ollama.com/api/chat)
and [tool-result replay](https://docs.ollama.com/capabilities/tool-calling).

Both prompts declare a writable scratch directory under isolated agent state.
Native write tools can create scripts there and run them by absolute path.
Bash here-docs are unsupported by this containment policy and this limitation
is stated in the prompt. No additional fixture files become writable; protected
tests, new workspace files, hidden verification and controller records retain
their OS denials. A brief final summary is requested after checks. Normal CLI
termination, timeout, transport failure, code verification and process cleanup
remain separate observations; passing code alone is never runtime success.

Offline qualification runs real pinned CLIs with synthetic provider responses.
It checks read/edit/search/public tests, denied accesses, scratch creation and
execution, final output and cleanup. Separate sleeping-child probes test the
parent deadline and refusal to restart a consumed attempt. Unit tests cover
stream/nonstream conversion, tool replay, output ceilings, malformed/partial
responses and preservation of unexpected thinking. They contact no model.

The existing Pi v0.3 provider settings are audited with
`node integrations/pi/audit-generation-request.mjs PREPARED_RUN OUTPUT_JSON`.
This copies its prepared model/settings to a fresh stub-only environment;
the prepared benchmark attempt is not executed. The recorded request, rather
than registry labels, determines which settings were actually transmitted.
Mini's native request construction is audited separately. Pi's old sandbox
only permits the direct Ollama port; a matched four-system experiment requires
a separately versioned Pi bridge/sandbox integration and qualification.

Live backend qualification uses a source-bound private one-shot plan, a fresh
30-second empty-state gate, exactly bounded simple text/tool probes, no retry
and an empty postflight. These are control/transport probes, not coding-task
reruns or speed measurements. The owner separately authorized stopping all
Ollama consumers and unloading models on 2026-10-18; two auto-restarting app
launch agents were removed from the current GUI session without changing
their plists. Their exact restoration paths are recorded privately.
