# Coding Track A v0.1 — cross-case report

Track A now contains three independent coding tasks, each attempted once by
the same five local Ollama deployments. No deployment dominated the set. The
results changed with task semantics, language, artifact transport and verifier
strength, which is more informative than a single aggregate winner.

## Scope

| Case | Language | Task family | Attempts | Primary result |
| --- | --- | --- | ---: | --- |
| Pagination cycle guard | Python | Bug fixing | 5 | 3/5 frozen v1.1 passes; 2 survive corrected-verifier replay |
| Async cache coalescing | JavaScript | Feature implementation | 5 | 0/5 verified successes |
| Payment-result migration | PHP | API migration | 5 | 0/5 strict artifacts; three code solutions confirmed in secondary or post-hoc transport checks |

The earlier five-attempt unified-diff pagination comparison is retained as a
separate transport pilot. It is not counted as a fourth task because the later
whole-file comparison repeats the same task and deployments with a different
artifact contract. Development smoke runs are also excluded.

This is a Capability Sweep: one attempt per deployment and task. The report
does not estimate reliability, stochastic quality or latency distributions.

## Primary frozen outcomes

The following table preserves exactly what each preregistered comparison
considered a successful delivered outcome.

| Deployment | Python v1.1 | JavaScript | PHP strict | Frozen successes |
| --- | --- | --- | --- | ---: |
| `qwen3.6:35b-a3b-mxfp8` | fail | fail | malformed | 0/3 |
| `qwen3.8:27b-mlx` | pass, later invalidated | fail, closest at 10/12 | malformed | 1/3 |
| `gpt-oss:20b` | empty | empty | empty | 0/3 |
| `muse-glimmer:30b-mlx` | pass | fail, 9/12 | malformed | 1/3 |
| `ornith-1.5:35b` | pass | fail, 5/12 | malformed | 1/3 |

The literal aggregate is 3 successes across 15 primary attempts. It is not a
useful model score. One success was later shown to be a verifier false positive,
and the PHP strict result is dominated by artifact transport.

## Best-known requirement evidence

This second view asks whether the exact saved code is known to satisfy every
currently tested requirement. It deliberately combines evidence layers and is
therefore diagnostic rather than a formal leaderboard.

| Deployment | Python with v1.2 verifier | JavaScript | PHP code semantics | Confirmed task outcomes |
| --- | --- | --- | --- | ---: |
| `qwen3.6:35b-a3b-mxfp8` | fail | fail | fail after transport normalization | 0/3 |
| `qwen3.8:27b-mlx` | fail | fail | pass, post-hoc transport audit | 1/3 |
| `gpt-oss:20b` | no artifact | no artifact | no artifact | 0/3 |
| `muse-glimmer:30b-mlx` | pass | fail | pass, post-hoc transport audit | 2/3 |
| `ornith-1.5:35b` | pass | fail | pass, preregistered secondary diagnostic | 2/3 |

The evidence labels matter:

- Pagination v1.2 is a retrospective replay of exact v1.1 artifacts, not a
  fresh preregistered comparison.
- The JavaScript results come directly from the frozen primary verifier.
- Ornith's PHP semantics were checked under a protocol frozen before the
  comparison; Qwen 3.8 and Glimmer were checked with transformations defined
  after their outputs were known.

Five of the 15 saved attempts therefore contain code confirmed by the best
currently available verifier, but that number must not replace the primary
comparison results.

## What the cases reveal

### Python: verifier strength changed the apparent ranking

The whole-file v1.1 verifier initially accepted Qwen 3.8, Ornith and Glimmer.
A post-hoc counterexample showed that Qwen 3.8 refetched a supplied non-empty
start cursor before raising the cycle error. Verifier v1.2 encoded the already
visible requirement and reduced the saved-artifact passes from three to two.

This is an eval-quality result as much as a model result: a weak verifier can
turn an incorrect solution into a silent success.

### JavaScript: all models crossed the transport floor except GPT-OSS

Four deployments delivered valid files and reached both test layers. None
handled the full concurrency contract. Qwen 3.8 came closest with 10/12 checks;
Glimmer reached 9/12. Their shared failures concerned invalidating an in-flight
load while allowing a new attempt to begin immediately.

This is the cleanest capability failure in the current coding set because the
stronger candidates were not stopped by artifact parsing.

### PHP: strict delivery and code semantics diverged

No deployment emitted the exact two-file envelope. Nevertheless, a frozen
secondary diagnostic confirmed Ornith's unchanged code at 12/12 tests, and
explicitly post-hoc byte-preserving audits confirmed Qwen 3.8 and Glimmer at
12/12. Qwen 3.6 still contained invalid PHP after its envelope was normalized.

The strict failures remain operationally real: an unattended Track A runner
could not install the responses. They should not be interpreted as four equal
PHP reasoning failures.

## Deployment observations

- **Ornith** has the broadest encouraging result in this small sample. It is
  verifier-confirmed on Python and PHP and had the shortest successful cold
  attempt in both cases. It still failed the JavaScript state model.
- **Muse Glimmer** is also confirmed on Python and PHP. Its answers and wall
  times were substantially larger in the observed successful cases.
- **Qwen 3.8** produced confirmed PHP code and was the closest JavaScript
  candidate. Its apparent Python success disappeared when the missing
  requirement became deterministic verification.
- **Qwen 3.6** delivered visible candidate code for every task but did not
  satisfy a complete current verifier.
- **GPT-OSS** used the entire 3,000-token generation budget for hidden
  reasoning and exposed no candidate in all three core runs. This identifies a
  poor fit between deployment settings and harness budget; it does not by
  itself prove absent coding knowledge.

## Speed is contextual evidence only

Ornith was the fastest deployment among the best-known successful Python and
PHP outcomes: 15.06 seconds and 20.07 seconds respectively. Qwen 3.8's
confirmed PHP code took 27.99 seconds, while Glimmer took 54.25 seconds on
Python and 67.81 seconds on PHP.

These are single cold attempts with different output lengths and load times.
They help select future experiments but cannot support P50, tail-latency or
reliability claims.

## Consequences for Track B

Track B should retain the same tasks and strongest available verifier while
changing only the harness. Two harness families will be reported separately:

1. a pinned Pi coding agent for practical external-harness fit;
2. a project-owned mini-harness with a small inspectable tool loop.

The first Track B question is not whether agents make every model succeed. It
is whether repository exploration, direct file writes and public-test feedback
move the observed capability boundary without weakening hidden verification.

The PHP task is especially diagnostic: tools may remove its response-envelope
floor. The JavaScript task tests whether iterative feedback can repair a real
behavioral error. Pagination carries verifier v1.2 so the known false positive
cannot silently return.

## Limits

- One attempt per deployment and task is insufficient for reliability claims.
- Language and task family change together, so their effects are confounded.
- The best-known matrix mixes formal and diagnostic evidence.
- Deployment size, quantization, runtime implementation and memory differ.
- No tested deployment was sufficient for the JavaScript task under Track A.

Accordingly, this report publishes matrices and failure modes rather than a
universal composite score or a declaration of the best coding model.
