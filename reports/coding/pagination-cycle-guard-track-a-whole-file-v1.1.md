# Pagination cycle guard — Track A whole-file v1.1

The whole-file contract removed the unified-diff format floor. Four of five
deployments returned valid replacement files and reached deterministic tests;
three passed the frozen verifier. A post-hoc requirement audit then found that
one of those three, Qwen 3.8, was a false positive for an explicit cursor-cycle
requirement.

## Results

| Order | Deployment | Valid artifact | Frozen verifier | Post-hoc start-cycle audit | Wall time |
| ---: | --- | --- | --- | --- | ---: |
| 1 | `gpt-oss:20b` | no | fail: empty output | not applicable | 39.85 s |
| 2 | `qwen3.6:35b-a3b-mxfp8` | yes | fail: hidden page-limit test | pass | 38.98 s |
| 3 | `qwen3.8:27b-mlx` | yes | **pass** | **fail: refetched start cursor** | 16.63 s |
| 4 | `ornith-1.5:35b` | yes | **pass** | pass | **15.06 s** |
| 5 | `muse-glimmer:30b-mlx` | yes | **pass** | pass | 54.25 s |

The preregistered result is therefore 3/5 frozen-verifier successes. After the
additional deterministic audit, only Ornith and Muse Glimmer have no known
counterexample, or 2/5. The latter is explicitly post-hoc and must not be
presented as though it were the original preregistered score.

## What changed from v1

V1 and v1.1 use the same task, repository fixture, visible context, inference
settings, public tests, hidden tests, deployment set and `CABED` positions. V1
required Git unified diffs; v1.1 required complete files in strict path
envelopes.

Under v1, all four visible responses failed patch application and no model
reached a test. Under v1.1, every visible response was a valid one-file artifact
and reached both test layers. The transport change therefore succeeded at its
intended purpose: behavioral verification could finally discriminate the
candidate implementations.

## Model-level findings

- GPT-OSS again exhausted all 3,000 output tokens in hidden reasoning and
  exposed no candidate artifact.
- Qwen 3.6 passed all public tests but failed the hidden exact-fetch-budget
  check because its code did not raise `PageLimitExceeded` after the final
  permitted call.
- Qwen 3.8 passed all ten frozen tests. Inspection suggested a missing initial
  `start_cursor` entry in its seen-cursor set. A direct diagnostic confirmed
  that a `resume → next → resume` cycle fetched `resume` twice before raising.
- Ornith passed all frozen and post-hoc checks in 15.06 seconds. Its response
  was byte-identical to the excluded successful smoke response.
- Muse Glimmer passed all frozen and post-hoc checks, but took 54.25 seconds
  and emitted 1,666 tokens versus Ornith's 385.

With a binary success criterion and the known counterexample excluded, Ornith
is the observed quality-latency choice on this single task. This is not yet a
reliability estimate or a general coding-model ranking.

## The verifier finding

Task requirement 4 says that a non-terminal cursor must never be fetched
twice. The frozen hidden suite tested cycles beginning from the default `None`
cursor, but not a cycle returning to a supplied non-empty `start_cursor`.
Qwen 3.8 exploited this gap accidentally: the test suite passed while the
candidate-visible requirement did not.

This is a concrete example of the project's earlier design warning:

> A weak verifier can turn a wrong small-model result into a silent pass.

The report does not mutate v1.1 or silently rewrite its frozen outcome. The
counterexample is labeled post-hoc. The proper repair is a new verifier version
with the missing case, followed by explicit decisions about replaying saved
artifacts and obtaining fresh attempts.

## Execution controls

All five deployment digests matched the frozen plan. Ollama was empty for the
30-second preflight, each candidate was unloaded after its attempt, and Ollama
remained empty through the 30-second postflight. News-App and the user-facing
Mnemosyn application were absent. Three Mnemosyn MCP helpers were idle; the
observed Behat infrastructure used only 0.07 CPU seconds during preflight.

Every elevated local-Ollama generation ended with verification pending. The
response hash and frozen case identities were then rechecked before candidate
code was executed by a separate workspace-sandbox command. No retry, repair,
warm-up generation or test feedback was used.

## Interpretation limits

There is one development task and one fresh attempt per deployment. These data
can show artifact-contract reachability and verified behavior for this case.
They cannot estimate performance tails, failure rates, quality stochasticity,
general coding superiority or a minimum sufficient model.
