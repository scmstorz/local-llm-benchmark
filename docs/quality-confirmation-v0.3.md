# Selected core text confirmation v0.3

This study asks whether the task-specific reasoning and source-fidelity findings
in the completed four-deployment core comparison recur under unchanged request
conditions. It does not introduce new cases, prompts, inference settings or
agent harnesses.

Execution and evaluation are complete. See the
[results and interpretation](../reports/quality-stochasticity/core-text-confirmation-v0.3.md).

## Selected conditions

| Case | Deployments | Fresh judged answers per deployment |
| --- | --- | ---: |
| Medical screening / Bayes | Ornith 1.5 and Qwen 3.8 | 3 |
| Grounded agentic-development writing | Ornith 1.5 and Nemotron 3.5 Lightning | 3 |

The writing pair is a targeted source-fidelity contrast, not a selection of the
two strongest writing candidates. Historical answers and judgments remain
separate pilot evidence and do not contribute to the new sample.

The immutable child plans stay with the private execution evidence because
they bind a private driver and contain the owner's literal authorization.
Their frozen SHA-256 identities are:

- Bayes: `1c1621332f22ab05b991e2fedb7e1b3588dd1ea4a8c60c6f222320d3bf4816eb`
- Writing: `45f53a48d87708142abfca57cce25e5d0efb1c8e77b249abf898202ababa0cdd`

The public protocol and aggregate expose the selected conditions, generation
settings, outcome layers and freeze provenance without those private records.

## Generation and execution

Each of the twelve measured warm answers immediately follows one fresh cold
generation on the same task and deployment. This retains the completed core
comparison's actual warm condition, including the preceding prompt execution.
An empty-prompt model preload is not substituted for that cold request.
Consequently, twelve quality observations require twenty-four native text
generations: twelve cold companions and twelve measured warm answers. Cold
companions are preserved but are not quality candidates.

Settings remain temperature 0, seed 42, thinking disabled, context 8,192 tokens,
output limit 2,600 tokens, keep-alive 10 minutes and request timeout 600 seconds.
The same exact deployment digests run on Ollama 0.40.5. This measures operational
repeatability with a fixed seed, not variation across seeds or temperatures.

The twelve pairs are interleaved in three four-condition blocks. Each condition
occupies three distinct positions within its blocks, and no adjacent pair uses
the same deployment. Three blocks cannot give perfect four-position balance;
the frozen order is not changed after observing any result.

Before every pair, the unchanged resource gate checks competing workloads,
exact runtime and digest, and an empty Ollama state over 30 seconds. Between
cold and warm requests, identity and absence of competing activity are checked
again. The selected model is unloaded after every pair and an empty postflight
is required before continuing. No unrelated consumer may be stopped without
the owner's permission.

A private, hash-bound driver calls the unchanged native `run_once` function.
It checkpoints the cold result before issuing the warm request. Started or
terminal pairs cannot automatically restart; failures and partial streams are
retained. A resource-gate pause before generation consumes no attempt. The
owner's explicit instruction to repeat the existing conditions is recorded in
a separate authorization binding the exact parent plan and driver before any
generation.

## Evaluation

The two existing task-specific rubrics and their source packets remain
unchanged. All fresh runtime-complete warm answers enter anonymized bundles;
technical failures remain explicit outcomes. Scalars are frozen before three
predeclared same-repetition pairs per case are reviewed. Both freezes precede
mapping reveal through [Evaluation Pipeline v0.2](quality-evaluation-v0.2.md).

Blinding is partial: the interactive judge has prior answer, score and error
exposure and can see orchestration. Fresh opaque candidate IDs and procedural
freezes do not establish independent cognitive blinding. No paid external judge
is used. Duplicate answers stay in the sample; their response hashes and scores
are reported transparently.

The interpretation explicitly checks whether Ornith repeats its reversed Bayes
mortality criterion or false-negative label, whether Nemotron repeats its
implementation-time/productivity reversal, and whether Ornith's observed writing
advantage persists. These are analysis targets under the existing rubric, not
new model-facing hints or new score caps.

Report each condition's individual scores, median, range, output identity,
material errors, deterministic checks and observed technical outcomes. Do not
infer precise failure probabilities, tail latency, statistical independence or
universal model rankings from three answers. Different judgments of an unchanged
historical answer are evaluator variation, not new model behavior.

Private requests, responses, mappings, process evidence and driver records stay
local. Public delivery uses the existing sanitized snapshot procedure.
