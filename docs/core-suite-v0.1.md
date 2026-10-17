# Provisional personal core suite v0.1

The task inventory is provisionally closed at **23 tasks in six families**.
Models are registered separately and can be added at any time. Harnesses are
separate versioned complete-system configurations. Structured extraction and
normalization is reserved for the next suite version.

| Family | Distinct tasks | Execution conditions |
| --- | ---: | --- |
| Summarization | 3 | Direct cold/warm pairs |
| Knowledge and transfer | 10 | Direct cold/warm pairs |
| Source-grounded writing | 2 | Direct cold/warm pairs |
| Coding | 3 | Direct, Mini v0.3, Pi v0.3 |
| Log investigation | 3 | Mini v0.5, Pi v0.5 |
| Multi-format decisions | 2 | Rollout: canonical, Mini v0.1, Pi v0.3; supplier: Mini v0.2, Pi v0.4 with evaluation 0.3 |

These are **35 task/system combinations per deployment**, rather than 35
independent tasks. Direct text is not multiplied across agent harnesses.
Supplier canonical extraction exists, but a standalone supplier Track A runner
is not admitted. OpenCode likewise has a qualification card but is not admitted.

The [task catalog](../tasks/core-suite-v0.1.json) fixes task membership and case
definition hashes. The [system registry](../capabilities/core-systems-v0.1.json)
maps those tasks to the existing lifecycle commands. A separately versioned
registry may add a qualified harness using `additional_case_ids`; this does not
require changing the task catalog or fixing a set of model names.

## One entry point, existing execution kernels

```bash
python3 -m local_llm_benchmark.core_suite overview
python3 -m local_llm_benchmark.core_suite first-comparison
```

These commands are offline. The [coverage inventory](../reports/core-suite-v0.1-coverage.md)
shows task versions, supported systems and links to historical evidence. A
historical measurement can include failures. It is not automatically a matched
baseline for a new runtime, task representation or evaluator. Supplier smoke
evidence is explicitly excluded and has not measured the corrected evaluator.

After selecting a candidate, register it and the reference under the same
current Ollama runtime. Registration reads metadata without loading a model or
running inference:

```bash
python3 -m local_llm_benchmark model-register \
  --models qwen3.8:27b-mlx CANDIDATE_TAG \
  --catalog models/CURRENT_CATALOG.json
```

Use the returned exact deployment IDs to generate a new plan. Any number of
distinct registered deployments is supported; this example binds two:

```bash
python3 -m local_llm_benchmark.core_suite plan \
  --catalog models/CURRENT_CATALOG.json \
  --deployments REFERENCE_DEPLOYMENT_ID CANDIDATE_DEPLOYMENT_ID \
  --profile first-comparison \
  --output results/core-suites/FRESH_COMPARISON

python3 -m local_llm_benchmark.core_suite commands \
  --plan results/core-suites/FRESH_COMPARISON/plan.json

python3 -m local_llm_benchmark.core_suite coverage \
  --plan results/core-suites/FRESH_COMPARISON/plan.json
```

Use `--profile full` for all 23 tasks. Planning creates an isolated directory,
a filtered text-suite manifest and command blocks. It binds exact digests,
one shared runtime version, task/system definitions, referenced fixtures,
prompts, evaluation contracts and runner source hashes. An existing output
directory is never overwritten. Changed source inputs prevent command export
from an old plan; create a separately named plan for changed conditions.

Command blocks are **instructions for the existing runners**. The planner
does not execute them. `prepare_runs_inference` identifies direct text/coding
commands that immediately make model requests. Agent preparation remains
offline; Mini then uses `call` and `step` until finalization, while Pi requires
fresh sandbox acceptance before `run` and `finalize`. Replace `{run_dir}` in
the lifecycle command arrays with the directory returned by preparation.
Run a text block once: it already covers every selected text case for that
deployment. Command export withholds the start command once the block has
observed execution, failure or partial evidence. Continue the existing run
lifecycle; the original text runner handles interrupted-suite resume. This
prevents the overview from inviting a terminal failure to be restarted.

Before any live block, verify current metadata against the bound plan, complete
the relevant fresh system/sandbox and resource checks, and obtain the concrete
plan authorization and exclusive machine window. Do not reuse old smoke
authorizations or stop competing services without the owner's required consent.
An installed model or metadata tools flag does not establish agent qualification.
The planner is not a new live resource controller or automatic retry policy.

## Supplier evaluation is selected before inference

Future supplier cells route through
`python3 -m local_llm_benchmark.supplier_execution`. Preparation binds
[execution configuration 0.3](../tasks/agentic/supplier-execution-v0.3.json),
verifier **2.1.0** and metrics **0.2.0**. The original Mini v0.2 and Pi v0.4
prompts, tools and extraction backend are reused, while the complete identity
records the separate evaluation configuration and its hashes.

Both real finalization kernels now invoke the corrected verifier through this
entry point. Normalized metrics are written with the completed fresh run:
artifact operations and completion are distinct, unavailable Pi request counts
stay null. The original standalone adapters retain their frozen evaluation.
The new entry point rejects historical runs without its preparation identity,
source drift and already completed runs; it cannot serve as a retrospective
score-repair command. The [earlier correction method](multi-format-verification-v0.3.md)
and frozen smoke scores remain authoritative for their own evidence blocks.

## First comparison, with candidate deliberately unselected

The [draft](../tasks/core-first-comparison-v0.1.json) contains one task per family:

1. METR research summary;
2. medical-screening Bayes explanation;
3. source-grounded agentic-development writing;
4. PHP payment migration, direct plus Mini and Pi;
5. clock-skew investigation with partial recovery, Mini and Pi;
6. supplier decision, Mini and Pi with corrected evaluation.

This is six distinct tasks and **ten cells per deployment**, hence twenty cells
for reference and candidate. Text cells use one cold/warm pair; warm is the
quality candidate. Other cells get one attempt. Agent requests depend on their
trajectories, so twenty cells is not twenty HTTP requests. Deployment order
rotates between command blocks. This is a bounded screen, not a balanced
reliability experiment. Repeat only separately selected decision-relevant
comparisons under a new repeated-study plan.

Qwen 3.8 is the proposed reference. The candidate and runtime stay null until
the owner selects the candidate and both current deployments are registered.
Historical observations do not fill this new comparison. A normal Ollama
update creates a new deployment condition; refresh the reference cells needed
for the specific comparison rather than automatically rerunning all history.

## Reading results

The coverage command reads only this plan's isolated result directories and
retains source hashes. It distinguishes not run, prepared, in progress,
execution failed, completed, identity mismatch, unrecorded partial attempts and
multiple ambiguous attempts. It never chooses the best of multiple results.
Completion means an execution record exists; a completed model failure still
counts as observed coverage. Quality review remains explicitly pending.

| Observable | Supported interpretation | Required separate assessment |
| --- | --- | --- |
| Deterministic checks / full pass | Required structured or executable behavior | Usefulness and grounded free-text claims |
| Strict transport | Declared output boundary was met | Semantic correctness |
| Runtime completion | Attempt terminated under its execution contract | Task success |
| Active time and recorded counts | Effort for this attempt and system | Efficiency per verified success and reliability distributions |
| Source-grounded rubric judgment | Quality for the frozen task/rubric | Universal model ranking |

Use the established joint text-judgment workflow and assess agent report prose
against supplied sources. Preserve grounding failures even when decisions are
correct. Report partial checks alongside all-required-check success, especially
for log investigations where a correct central diagnosis can miss evidence
roles. Do not combine these layers into a universal score or equate `n=1`
with a reliability rate. Coverage bookkeeping does not certify hidden run
artifacts; existing finalizers and the separate quality review remain required.
