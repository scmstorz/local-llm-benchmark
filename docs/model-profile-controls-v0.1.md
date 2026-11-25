# Technical model-profile controls v0.1

Step1 makes the jointly agreed starting profiles configurable and qualifies
the model boundary. Quality calibration and final profile/harness selection
remain separate joint steps. The historical external CLI v0.3 off profile and
all old contracts/results remain unchanged.

The [candidate registry](../models/practical-profiles-v0.1.json) binds each
profile to an exact installed model digest and Ollama version. It includes
Qwen3.8 xhigh and medium, Gemma4 thinking on, Nemotron Lightning thinking on
and Ornith native reasoning via an explicit boolean request. The source cards
and model-specific sampling settings are recorded in each candidate. These
are starting candidates, with no claim of optimal quality.

Context capacity, combined reasoning/answer output ceiling and seed have no
implicit defaults. Build an explicit condition without starting inference:

```sh
python3 -m local_llm_benchmark.model_profiles list
python3 -m local_llm_benchmark.model_profiles build \
  --profile qwen38-27b-xhigh-v1 --context 32768 --output 8192 --seed 42
```

Those capacities illustrate the builder; they are not agreed performance
settings. The resulting condition can be passed as `profile` to
`external_cli_provider.ProviderJournal`. This is a new opt-in provider condition;
the default forwarding path and the fixed v0.3 condition retain their behavior.
It does not yet configure Pi, Mirror, Vibe or another complete harness to use
the practical profiles. That integration follows profile selection in step3.

Before forwarding a generation, the new condition verifies runtime version,
exact model artifact, advertised capabilities, supported thinking value and
architecture context capacity using metadata-only calls. It rejects unsupported
named modes instead of silently accepting a fallback. Ornith lacks advertised
thinking metadata; only the explicitly marked boolean-positive qualification
path is allowed. Positive returned thinking is established for this artifact
in the qualification report; no named level is invented.

The bridge records the original client body, effective native `/api/chat` body,
both response sides, condition binding, metadata admission and history audit.
Every generation, including a context summary, receives the chosen thinking
and sampling controls and explicit context/output settings. Smaller client
ceilings are honored. Conflicting client settings fail. Stream/nonstream
responses preserve reasoning, tool correlation, usage and finish reason.
Truncation stays `length`; it is never renamed to normal completion.

Reasoning history supplied by a caller is preserved by default. Gemma retains
tool-call reasoning within the current user turn and drops reasoning from
older turns and ordinary past answers. Its
[model card](https://ai.google.dev/gemma/docs/core/model_card_4) and the installed
[Ollama0.40.5 renderer](https://github.com/ollama/ollama/blob/v0.40.5/model/renderers/gemma4.go)
define the relevant behavior. Each change
is counted in the audit. Missing caller history is never reconstructed. A
complete harness still needs its own replay qualification. Native API behavior
is documented in Ollama's [thinking](https://docs.ollama.com/capabilities/thinking)
and [tool-calling](https://docs.ollama.com/capabilities/tool-calling) guides.

Wire evidence proves requested settings and backend acceptance. Returned
reasoning and observed `/api/ps` context are checked separately. A capacity
audit records the observed prompt count and remaining room after reserving
the requested output; architecture maximum and runtime allocation are distinct.
These controls do not statistically prove a sampling distribution, stochastic
reproducibility or a reasoning level's quality advantage.

The bounded step1 technical plan has five independent conditions, each with a
fresh30-second idle gate, fixed source/runtime/artifact bindings and no retry.
Each condition requests a short reasoning/text answer, a tool call, replay of
its result and reasoning history, and an intentional one-token truncation.
A controlled marker supplied only inside the tool-call reasoning tests positive
history transport. It is an injected protocol canary, not model-generated
reasoning or task evidence. Each run records the actual backend context and
unloads only its own admitted model afterwards.

Technical probes use context32768, output ceiling4096 for the three functional
requests, then a smaller client ceiling1 for truncation, seed42, provider
socket timeout300 seconds and a600-second monotonic unit budget. The
budget is checked before requests; a separate hard watchdog is not qualified
by these model-boundary probes. These are bounded
control-test capacities, not adopted performance budgets. No knowledge,
document or coding benchmark case is run, and no quality ranking is computed.
Step2 tasks, repetitions, budgets and selection rules remain owner decisions.

The initial fixture added a new user message after the tool result. That closes
Gemma's reasoning-history scope, so this fixture is unsuitable as a universal
positive replay test. Its20 original generations and all failures are preserved.
The implementation now makes Gemma's user-turn boundary explicit. A separately
source-bound protocol revision checks same-turn continuation for Gemma,
Nemotron and Ornith, retaining tool declarations and placing continuation
instructions before the tool call. It permits at most six generations plus
nine render-only inspections; it does not restart a consumed attempt.

The pinned server's
[`_debug_render_only` implementation](https://github.com/ollama/ollama/blob/v0.40.5/server/routes.go)
can show the actual rendered prompt without generation. Paired inspections with
and without a supplied marker establish its presence directly; an additional
inspection records behavior across a new user-turn boundary. Render-only calls
and generations are counted separately. No runtime or model artifact is changed.

Ornith's installed Jinja template reads `reasoning_content` or extracts a
`<think>` block from assistant content; it ignores the native `thinking` field.
The first render-only probe demonstrated identical prompts with/without that
field. Its exact-artifact profile therefore uses `content_think_tags` replay,
following the fallback in the [official template](https://huggingface.co/ornith-ai/Ornith-1.5-35B-A3B/blob/main/chat_template.jinja).
This encoding changes only supplied assistant history; it does not invent
reasoning. Ambiguous embedded thinking delimiters fail explicitly. Other
profiles retain native `thinking` replay. Both representations are journaled.

The same-turn follow-up completed four generations and six render-only calls:
Gemma passed; Nemotron's first native stream ended with `{"error":"EOF"}`;
Ornith's unencoded reasoning was absent from the rendered prompt, so its second
generation was skipped. These failures remain immutable. A final independent
replay fixture permits at most two generations and six render-only calls for
Nemotron/Ornith. It stages a declared synthetic assistant tool call and reasoning
canary, then checks the actual prompt and one continuation. It does not retry
Nemotron's failed tool-call generation or change sampling/capacities. Backend
errors are retained explicitly in the new condition's journal.

Completed evidence: [technical report](../reports/model-profile-controls-v0.1.md).
The staged Nemotron/Ornith replay checks both pass. Totals are26 generation
requests (25 completed, one native backend abort) and12 render-only calls.
The observed failures remain part of the result; this is not a reliability
estimate or a scored quality comparison.
