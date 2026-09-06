# Model catalog and recurring onboarding

New local models are expected, not exceptional. Task-suite manifests therefore
do not contain a closed model list. The tracked
[`catalog.json`](catalog.json) records exact Ollama deployment identities, while
separate cohort manifests bind selected deployments to a versioned task suite.

Deployment identity and current selection policy are intentionally separate.
[`lifecycle.json`](lifecycle.json) defines which registered model tags enter a
new regular sweep. The default selection can be inspected without contacting
Ollama:

```bash
python3 -m local_llm_benchmark.model_lifecycle
```

The current default cohort is Qwen 3.6, Qwen 3.8, Muse Glimmer, Ornith and
Gemma. Nemotron is opt-in as a speed specialist, Granite is diagnostic-only,
and GPT-OSS is retired from active cohorts. A retired model is not deleted or
uninstalled: its immutable catalog entries, raw runs, reports and frozen plans
remain reproducible. GPT-OSS may be selected again only in a preregistered
negative-control role:

```bash
python3 -m local_llm_benchmark.model_lifecycle \
  --status retired_from_active_cohort
```

Register one or more installed models without loading them or running
inference:

```bash
python3 -m local_llm_benchmark model-register --models \
  granite4.2:30b \
  nemotron-3.5-lightning:30b-mlx \
  gemma4:31b-mlx
```

Registration reads only Ollama's version and installed-model metadata. It is
idempotent for the same tag, digest and Ollama version. If a tag later resolves
to a different digest, the command appends another deployment instead of
overwriting the historical identity.

The recurring Track A workflow is:

1. register the exact deployment;
2. add it to a dated cohort or run it independently against the unchanged
   suite manifest;
3. preserve the raw cold and warm results in a new sweep;
4. assemble one blinded evaluation batch for all newcomers in that cohort;
5. judge before opening the private candidate mapping;
6. derive a new report without rewriting canonical historical comparisons.

Run any registered or newly installed deployment through the current suite:

```bash
python3 -m local_llm_benchmark suite \
  --model granite4.2:30b \
  --suite tasks/capability-suite-v0.3.json
```

If the process ends while a case is still `running`, resume the same sweep:

```bash
python3 -m local_llm_benchmark suite-resume \
  --sweep-dir results/sweeps/SWEEP-ID
```

Completed cases are never repeated. Explicitly failed cases remain failures and
are not retried. An unfinished case is restarted as a fresh cold/warm pair, but
its partial case record and any raw run artifacts remain append-only evidence
under `interrupted_attempts`. The command rejects changed suite hashes, model
digests, Ollama versions, case positions and methodology settings.

After all cohort sweeps complete, repeat `--sweep-dir` to create one joint
quality batch:

```bash
python3 -m local_llm_benchmark challenger-bundles \
  --sweep-dir results/sweeps/SWEEP-GRANITE \
  --sweep-dir results/sweeps/SWEEP-NEMOTRON \
  --sweep-dir results/sweeps/SWEEP-GEMMA
```

The assembler derives the candidate count per case instead of assuming five
candidates. This matters because the canonical writing comparisons already
contain Ornith while the earlier comparisons contain four incumbents.
All supplied newcomer sweeps must reference the same exact suite-manifest hash;
the assembler also rechecks every run's case, prompt and source identities and
its model/digest binding before creating a bundle.

Catalog registration establishes identity only. Completion capability makes a
deployment eligible for the direct Track A text sweep, but no catalog entry is
automatically qualified for Mini, Pi, OpenCode or another Track B harness.
Native-tool capability advertised by Ollama is recorded as discovery evidence,
not as a successful agent-harness test. Registration also does not imply
current active-cohort selection; new experiment plans must consult the
lifecycle registry and record any explicit opt-in exception.

The first reusable newcomer cohort is frozen in
[`cohorts/capability-suite-2026-09-02.json`](cohorts/capability-suite-2026-09-02.json).
Its three deployments completed all 90 planned cold and warm requests. The
joint blind evaluation admitted `gemma4:31b-mlx` as a strong Track A candidate;
Nemotron and Granite remain useful diagnostic evidence but did not qualify as
general-purpose additions. See the tracked
[`execution record`](../reports/challenger-sweeps/september-2026-model-cohort-execution.md)
and [`quality report`](../reports/challenger-sweeps/september-2026-model-cohort-quality.md).
