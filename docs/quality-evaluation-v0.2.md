# Quality Evaluation Pipeline v0.2

The v0.2 pipeline turns blinded interactive judgment into a checked,
irreversible workflow. It is additive to the frozen v0.1 study controller: old
studies and their historical reports remain unchanged, while future studies
can use this pipeline to validate judge outputs and generate aggregates.

The design goal is simple: scalar scores must be final before pairwise review,
and both judgment layers must be immutable before model identities or runtime
measurements become available to the aggregation step.

## Phase boundary

The state machine has four monotonic phases:

```text
initialized
    -> scalar_frozen
    -> pairwise_frozen
    -> revealed
```

Before `revealed`, the implementation reads only anonymized judge bundles and
the submitted judgment files. It does not read `study.json`, either private
candidate map, deployment identities, run IDs, or performance measurements.
The pre-reveal `status` output exposes only phase, expected counts, and freeze
hashes.

Each transition validates the current bundle fingerprints and every previously
frozen artifact. A changed or missing freeze stops the pipeline. Existing
freeze and output files are never overwritten.

## Supported judge schemas

Scalar results are validated against the exact `judge-result.schema.json`
copied into each anonymized bundle. The project contains a dependency-free
validator for the closed JSON Schema subset used by those contracts:

- local `$ref` and `$defs`;
- object properties, required fields, and closed objects;
- arrays, item schemas, item bounds, and uniqueness;
- strings, regular expressions, minimum length, and RFC 3339 date-times;
- numeric bounds; and
- `const`, `enum`, and the JSON primitive types.

Unknown assertion keywords fail closed. This validator is intentionally not a
general implementation of JSON Schema.

Every candidate must have exactly one result. Candidate IDs and evaluation IDs
must be unique, the case-specific schema must pass, and the submitted
`deterministic_checks` object must equal the checks frozen in the bundle as a
JSON value. Missing, duplicate, unexpected, or altered candidates reject the
complete scalar freeze.

## CLI workflow

Initialize an evaluation after the study controller has produced its judge
bundles:

```bash
python3 -m local_llm_benchmark.quality_evaluation_v02 init \
  --study-dir results/quality-stochasticity/studies/STUDY-ID
```

Place one complete schema-valid JSON judge result per candidate in a dedicated
directory. Files may be grouped in subdirectories; every `.json` file below
the supplied directory is treated as a result.

```bash
python3 -m local_llm_benchmark.quality_evaluation_v02 freeze-scalars \
  --study-dir results/quality-stochasticity/studies/STUDY-ID \
  --results-dir /path/to/blind-scalar-results
```

The command creates `evaluation-v0.2/scalar-freeze.json`, records its SHA-256
digest, and advances the state only after all candidates pass validation.

Pairwise input has one record for every pair in every bundle's frozen
`pairwise-plan.json`:

```json
{
  "schema_version": "quality_evaluation_pairwise_input_v0.2",
  "comparisons": [
    {
      "case_id": "summarization.dev.example",
      "pair_id": "pair-S-1",
      "repetition": 1,
      "candidate_a": "candidate-opaque-a",
      "candidate_b": "candidate-opaque-b",
      "preference": "A",
      "rationale": "A preserves the decisive caveat more precisely."
    }
  ]
}
```

Candidate orientation is part of the frozen contract. Preference must be
`A`, `B`, or `tie`. Pairwise review cannot alter scalar scores.

```bash
python3 -m local_llm_benchmark.quality_evaluation_v02 freeze-pairs \
  --study-dir results/quality-stochasticity/studies/STUDY-ID \
  --results /path/to/blind-pairwise-results.json
```

Only after both freezes exist may the mapping be opened:

```bash
python3 -m local_llm_benchmark.quality_evaluation_v02 reveal \
  --study-dir results/quality-stochasticity/studies/STUDY-ID
```

Optional `--aggregate-json` and `--report` arguments can place the public-safe
aggregate and generated Markdown report at reviewed repository paths. Without
them, all outputs remain below the ignored study directory.

At any point, verify the current state and hashes without inference:

```bash
python3 -m local_llm_benchmark.quality_evaluation_v02 status \
  --study-dir results/quality-stochasticity/studies/STUDY-ID
```

## Reveal outputs

Reveal writes three distinct artifacts:

- a private per-candidate join containing the candidate mapping, run identity,
  judgments, checks, and performance measurements;
- a public-safe JSON aggregate without candidate IDs, run IDs, raw responses,
  private paths, or judge rationales; and
- a public-safe Markdown summary generated only from that aggregate.

The aggregate separates:

- quality scores, verdicts, deterministic compliance, and usable-output count;
- response variation and byte-identical group sizes;
- error types, severities, known error IDs, and recurring errors;
- pairwise wins, losses, and ties;
- technical completion and classified failures; and
- wall time, time to first content, generation duration, and output throughput.

For small samples it reports every score plus mean, median/P50, sample standard
deviation, minimum, and maximum. It does not calculate P90, P95, P99, or a
precise reliability probability. No composite quality-speed-reliability score
is produced.

## Interpretation limits

This pipeline makes the procedural order testable; it cannot guarantee that a
human judge did not infer identity from writing style or repeated content.
Per-candidate deterministic checks required by the rubric remain visible, but
cross-candidate statistics, model identity, and performance metadata remain
hidden until reveal.

The interactive judge is still a source of judgment variance. Hashing proves
which evaluation was frozen and when the pipeline allowed the reveal; it does
not prove that the rubric itself is valid. Calibration against source-grounded
examples and occasional independent review remain necessary.
