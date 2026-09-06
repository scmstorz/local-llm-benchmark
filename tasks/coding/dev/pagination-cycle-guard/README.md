# Pagination cycle guard

Case ID: `coding.dev.pagination-cycle-guard`

This is the first bounded coding case and the first Track A development
fixture. It asks a model to repair a small Python package that
collects records from a cursor-paginated source.

## Current state

The immutable direct-patch contract is frozen as version `1.0.0`. Its
post-smoke five-model Capability Sweep was executed according to
`comparison-plan.json`. All five inference attempts completed, but none
produced an applicable patch; the observed verified success rate is therefore
zero of five. The earlier Ornith smoke remains excluded from the formal
comparison.

A separate version `1.1.0` is now implemented in
`case-whole-file-v1.1.json`. It uses the same task, fixture manifest, visible
repository files, inference defaults, public tests and hidden tests, but asks
for strict complete-file replacement envelopes. Its reference repair passes
both deterministic test layers. The first Ornith development smoke also passed
all 4 public and 6 hidden tests. That observed attempt is excluded from the
separately executed five-model v1.1 comparison.

Verifier/case version `1.2.0` is implemented separately in
`case-whole-file-v1.2.json`. It leaves the visible task, prompt, fixture,
public tests and whole-file contract unchanged, but adds the hidden scenario
that cycles from a supplied non-empty `start_cursor` back to that cursor. The
baseline remains red and the reference repair passes all 4 public and 7 hidden
tests. A retrospective replay made no inference requests: it caught Qwen 3.8's
known v1.1 false positive, retained Qwen 3.6's existing page-limit failure and
left Ornith and Glimmer green. These replay outcomes are diagnostic and do not
replace the frozen v1.1 result.

## Why this case

The defect is small enough to validate the new execution path, but it is not a
single-token or syntax repair. A correct patch must simultaneously handle:

- overlap within and between pages;
- empty non-terminal pages;
- repeated-cursor cycles;
- a strict page-fetch budget;
- stable error types and observable side-effect boundaries.

The task therefore tests causal control-flow reasoning and boundary handling
without requiring a large repository or framework-specific knowledge.

## Track A contract

The candidate receives `TASK.md` plus the exact files listed in `case.json`.
It has no tools and cannot browse the repository. Its entire visible response
must be one Git-style unified diff, optionally enclosed in a single `diff`
code fence.

Only files below `src/paged_sync/` may change. The controller applies the patch
to a disposable fixture copy. It then runs the visible tests and a separate
hidden acceptance suite. Modifying tests, metadata or task files is a failed
outcome even if the code otherwise passes.

## Track A v1.1 whole-file contract

Version `1.1.0` accepts one to three existing files in this exact envelope:

```text
<<<FILE path="src/paged_sync/example.py">>>
complete file content
<<<END FILE>>>
```

No prose, Markdown fence, partial snippet or duplicate path is accepted. The
controller validates normalized paths, rejects new and protected files,
installs the complete candidate content with one canonical final newline and
then runs the same public and hidden behavior tests as v1. It never repairs
candidate code.

V1 and v1.1 answer different questions and must not be pooled. V1 includes the
ability to serialize a directly applicable Git patch; v1.1 focuses more
narrowly on producing correct replacement source code.

## Success definition

`verified_success` requires all of the following:

1. non-empty output that is parseable under the selected artifact contract;
2. candidate paths entirely inside the allowed source scope;
3. successful artifact installation;
4. no protected or undeclared file changes;
5. all public tests pass;
6. all hidden acceptance tests pass.

No partial 100-point quality score is primary for this case. Runtime success,
output validity, verifier success and task success remain separate fields.

## Frozen comparison protocol

The first Track A comparison gives each of the five current deployments one
fresh post-freeze attempt in the authoritative `CABED` order. Every model is
explicitly unloaded before its request, and no warm-up generation is used.
There are no automatic retries, adaptive repeats or controller-side patch
repairs. A malformed patch, failed application or failed test is retained as
the model's outcome.

The single observations support a Capability Sweep only. Cold wall time and
Ollama timing fields remain useful diagnostics, but they do not estimate
steady-state performance, tail latency or reliability.

The comparison exposed a format floor: every non-empty candidate failed before
tests because its unified diff was not applicable. Version `1.0.0` remains
unchanged evidence. The implemented v1.1 whole-file contract isolates code
generation from diff-hunk serialization and will be reported separately.

The v1.1 comparison plan reuses the v1 `CABED` order so every deployment holds
the same position in the paired artifact-contract comparison. It allows one
fresh cold attempt per model, no retries, no repair and no test feedback. Plan
freezing did not authorize generation; the comparison was subsequently run
after explicit approval.

Four of five deployments returned valid artifacts. Qwen 3.6 failed a hidden
page-budget test; Qwen 3.8, Ornith and Glimmer passed the frozen verifier. A
post-hoc task-derived audit then demonstrated that Qwen 3.8 refetches a supplied
non-empty start cursor in one cycle scenario. The tracked v1.1 report preserves
both the preregistered 3/5 verifier result and the separately labeled 2/5
outcomes without a known counterexample. The separately versioned v1.2 suite
now covers this missing case; see its retrospective replay
[`report`](../../../../reports/coding/pagination-cycle-guard-verifier-v1.2-retrospective-replay.md).

## Execution safety

The verifier imports and executes the patched package. Its disposable fixture
copy prevents benchmark-state contamination but is not a security sandbox.
Runs initiated through Codex inherit the surrounding execution sandbox. When
Ollama itself requires elevated local-network access, use deferred verification
so the elevated generation process only persists text and the later sandboxed
command executes the candidate. A standalone runner must add an explicit OS or
container boundary before it is used for untrusted third-party patches.
