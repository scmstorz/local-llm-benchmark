# PHP payment-result migration — Track A comparison

The preregistered five-model Capability Sweep is complete. Its primary strict
result is 0/5 verified successes. A frozen secondary diagnostic and a separately
labeled post-hoc audit show that this strict result conceals substantial code
capability.

## Method

The comparison followed the frozen `BCEDA` order: Qwen 3.8, GPT-OSS, Ornith,
Muse Glimmer and Qwen 3.6. Every deployment received one fresh cold attempt
with temperature zero, seed 42, thinking disabled, a 16,384-token context and
a 3,000-token output limit. No retry, repair, warm-up or test feedback occurred.
The earlier Ornith smoke remained excluded.

The resource gate found matching model digests, empty Ollama state and no
News-App or Mnemosyn application worker. Three Mnemosyn MCP helpers accumulated
no CPU time. Idle Behat infrastructure advanced by about 0.04 CPU seconds and
`fseventsd` by 0.12 seconds over 30 seconds. Every model was unloaded after its
attempt, and Ollama remained empty through the 30-second postflight.

## Three distinct outcome layers

1. **Primary:** the unmodified response must satisfy the strict envelope and
   pass all tests.
2. **Preregistered secondary:** only fence-only malformed responses eligible
   under the frozen, code-byte-identical transport protocol.
3. **Post-hoc audit:** result-specific minimal transport counterfactuals defined
   after outputs were known. These are exploratory and never replace layers 1
   or 2.

## Results

| Pos. | Model | Wall time | Strict outcome | Preregistered secondary | Post-hoc code semantics |
| ---: | --- | ---: | --- | --- | --- |
| 1 | Qwen 3.8 | 27.99 s | malformed: blank line between envelopes | ineligible | 12/12 pass |
| 2 | GPT-OSS | 41.39 s | empty after 3,000 reasoning tokens | ineligible | unavailable |
| 3 | Ornith | 20.07 s | malformed: Markdown PHP fences | 12/12 pass | not needed |
| 4 | Muse Glimmer | 67.81 s | malformed: `>>` instead of `>>>` | ineligible | 12/12 pass |
| 5 | Qwen 3.6 | 29.76 s | malformed: blank line between envelopes | ineligible | 0/4 public, 2/8 hidden |

The primary result remains **0/5**. No strict candidate tests ran because none
of the four visible outputs crossed the frozen transport boundary. GPT-OSS
again exhausted its output budget in hidden reasoning and emitted no candidate.

## Preregistered transport diagnostic

Ornith's fresh response was byte-identical to its excluded smoke response. It
contained exactly two PHP fences, so the frozen diagnostic mapped the unique
class names to the two allowed paths, removed only fence lines and added only
the required markers. Per-file hashes remained identical. The exact code then
passed all four public and eight hidden checks.

This does not make the primary Ornith attempt successful. It establishes the
separate, preregistered fact that its code semantics satisfy the current
verifier despite failed automated delivery.

## Clearly post-hoc semantic audit

After all primary and preregistered outcomes were known, three additional
zero-inference checks tested the other visible responses. These transformations
were result-specific and therefore cannot enter the formal comparison:

- Qwen 3.8: remove exactly one blank line between two already path-bearing
  envelopes. The byte-identical code passed 12/12.
- Muse Glimmer: add exactly one missing `>` to each opening marker. The
  byte-identical code passed 12/12.
- Qwen 3.6: remove exactly one blank line between envelopes. The byte-identical
  code reached the tests but failed with a PHP parse error, passing 0/4 public
  and only the two independent RetryPolicy hidden checks.

The exploratory semantic picture is therefore three verifier-confirmed code
solutions, one code failure and one absent output. Ornith was fastest among the
three semantic successes at 20.07 seconds cold wall time, followed by Qwen 3.8
at 27.99 seconds and Glimmer at 67.81 seconds. One run each is not performance
or reliability evidence.

## Interpretation

The strict result and semantic audit answer different questions:

> None of the models delivered an immediately machine-consumable strict
> artifact, but Qwen 3.8, Ornith and Glimmer generated PHP code that passes the
> complete current verifier after code-byte-identical transport normalization.

This case exposed a harness floor rather than merely ranking PHP skill. The
strict failures are real operational failures: an unattended system could not
install these responses under the declared grammar. At the same time, an exact
parser that rejects one inter-envelope blank line is too brittle to be the sole
measure of intrinsic coding capability.

The result should remain immutable. A future version may adopt a
whitespace-tolerant explicit-path grammar or structured output, while Track B
file-writing tools can test whether a real agent harness removes this transport
bottleneck. Neither change should rewrite this v1 comparison.

## Limits

This is one PHP task and one attempt per deployment. It does not estimate
general PHP capability, stochastic reliability or latency distributions. The
post-hoc audits are transparent diagnostics, not preregistered secondary
outcomes and not grounds for changing the primary 0/5 result.
