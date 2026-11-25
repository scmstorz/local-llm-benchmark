# Model-profile controls v0.1: technical qualification

The five agreed starting candidates are configurable and have positive
model-boundary control/history evidence. They remain starting candidates for
joint quality calibration. No complete practical harness configuration or
best-quality profile has been selected.

| Candidate | Explicit thinking | Text/tool call | Context/output controls | Positive history fixture |
|---|---|---|---|---|
| Qwen3.8 27B MLX | xhigh | pass | pass | Cross-user canary recalled |
| Qwen3.8 27B MLX | medium | pass | pass | Cross-user canary recalled |
| Gemma4 31B MLX | true | pass | pass | Same-user tool continuation |
| Nemotron3.5 Lightning30B MLX | true | pass | pass | Staged same-user tool history |
| Ornith1.5 35B Q4_K_M | true | pass | pass | Staged history with template-compatible encoding |

These are different technical fixtures, not quality scores or a speed ranking.
The [registry](../models/practical-profiles-v0.1.json) binds manufacturer-informed
sampling, thinking and history handling to the exact four installed artifacts
and Ollama0.40.5. Context/output capacity and seed must be supplied explicitly.
[Method and API usage](../docs/model-profile-controls-v0.1.md);
[machine-readable results](model-profile-controls-v0.1.json).

The provider records original/effective requests, both response sides, exact
metadata admission, supplied/dropped history, usage and finish reasons. Runtime
context32768 was observed; intentional one-token output caps were honored and
reported as `length`. Returned thinking was observed for every candidate.
The4096-output ceiling, seed42 and bounded technical time limits are probe
settings, not adopted performance budgets.

Three protocols and their failures are retained separately:

- Initial series:20 generation requests. All controls passed. The extra history
  fixture incorrectly introduced a new user turn as a universal positive test:
  Gemma/Nemotron reached4096 tokens and Ornith did not recall the marker.
- Same-user revision:four generation requests and six render-only inspections.
  Gemma passed. Nemotron's native stream ended with `{"error":"EOF"}` before
  a tool response completed. Ornith's thinking field was absent from its actual
  rendered prompt, so its continuation was skipped.
- Independent staged tool-history fixture:two generation requests and six
  render-only inspections. Nemotron and corrected Ornith passed. The assistant
  reasoning/tool call was explicitly synthetic, not generated evidence or a
  retry of Nemotron's failed tool-call generation.

In total:26 generation requests,25 completed, one backend abort and12
render-only calls without generation. No consumed plan was restarted. The
successful staged Nemotron continuation does not erase its backend failure.

Gemma retains tool-call reasoning within the current user turn. The pinned
[Gemma renderer](https://github.com/ollama/ollama/blob/v0.40.5/model/renderers/gemma4.go)
and the live prompt checks establish that boundary. Nemotron's prompt also
omitted the canary after a new user turn. Ornith's native template ignored the
`thinking` field; the artifact-bound translator now uses the content-block
fallback in its [official template](https://huggingface.co/ornith-ai/Ornith-1.5-35B-A3B/blob/main/chat_template.jinja).
Ambiguous thinking delimiters are rejected. The pinned
[render-only server path](https://github.com/ollama/ollama/blob/v0.40.5/server/routes.go)
lets us inspect these prompts separately from model answers. A caller's
forwarded history alone is insufficient evidence of actual model context.

Verification:729 regression tests pass with six expected opt-in skips;
49 focused tests and four legacy native tool/deadline cells pass. All411
previously frozen source artifacts, four historical Mirror/Vibe runs and the
20 original probes remain unchanged. All10 unit postflights and the final
Ollama check are empty. Source freezes and evidence hashes are in the JSON.
Raw responses, rendered prompts and synthetic canaries remain in private
`results/agentic-dry-runs/profile-qualification-v0.1/technical-20261018T102628Z/`.

Next: owner feedback, then jointly define step2 calibration cases, repetitions,
capacities and selection rules; plan step3 profile freeze and qualification
through the selected harnesses. No quality calibration or performance sweep
has started. Sampling distributions and reasoning-level quality differences
are not established by these transport probes.
