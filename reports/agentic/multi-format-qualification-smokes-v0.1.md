# Multi-Format Qualification Smokes v0.1

Status: complete with versioned Pi recovery. This is excluded qualification
evidence, not a measured comparison.

## Outcome

The accepted complete systems are `mini-multi-format-v0.1` and
`pi-multi-format-v0.3`. Both produced terminal reports that passed all 11
deterministic semantic checks.

| System | Runtime | Semantic | Strict transport | Turns | Tool calls | Active time |
| --- | --- | --- | --- | ---: | ---: | ---: |
| Mini v0.1 | pass | 11/11 | pass | 17 | 16 | 125.99 s |
| Pi v0.3 | pass | 11/11 | fail | 6 | 17 | 125.87 s |

Pi's final response contained surrounding text. Deterministic normalization
recovered one intact schema-valid report, so semantic verification passed while
strict transport correctly remained false. These are separate outcomes.

## Preserved Pi preflight failures

The original Pi v0.1 real Seatbelt acceptance failed before Pi or model
inference because Homebrew's admitted Python framework launcher attempted to
spawn the unlisted `Python.app` worker. V0.2 executed that exact worker
directly and passed all 11 original Seatbelt checks, but Pi then rejected the
case-sensitive worker basename while loading the extension. That run ended
with zero agent turns, tokens and tool calls.

Neither system was retried or overwritten. V0.3 is a distinct identity that
accepts the exact `Python.app` worker and adds a twelfth pre-inference check:
the explicit extension and policy must load successfully beneath the real
Seatbelt profile. The final V0.3 acceptance passed 12/12.

## Boundary

The smokes used one Qwen 3.8 deployment under Ollama 0.33.2, with a 30-second
empty-state gate before each executed system and model unload afterwards. The
final postflight contained no loaded model. There were no automatic retries.

The smoke gate permits design of a separate measured Track A/Track B plan. It
does not itself authorize measured execution, enter any measured aggregate,
support a performance ranking, or turn the complete-system comparison into a
one-factor harness experiment.
