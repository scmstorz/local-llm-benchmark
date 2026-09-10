# Changelog

Repository releases use project-level versions. Task, dataset, prompt, verifier,
harness, and study-protocol versions are independent immutable identifiers. A
task named `v0.5` therefore does not imply project release `v0.5.0`.

## Unreleased

### Added

- a complete Performance and Reliability Study v0.1 with 80 measured requests,
  separate natural and controlled-decode workloads, per-attempt raw metrics,
  exploratory P90 reporting and an explicit notebook-standby sensitivity view;
- a design-complete, execution-locked multi-format decision case with separate
  canonical-representation and real-artifact conditions, strict structured
  output, controlled ground truth and 11 deterministic semantic checks;
- Evaluation Pipeline v0.2 with schema-valid scalar imports, exact candidate
  coverage, immutable SHA-256-bound scalar and pairwise freezes, and a
  model-mapping reveal that is unavailable before both judgment phases finish;
- dependency-free validation for the closed JSON Schema subset used by frozen
  judge-result contracts;
- automatic public-safe JSON and Markdown aggregation that keeps quality,
  response variation, judged errors, pairwise preference, runtime reliability,
  and performance separate; and
- regression tests for phase ordering, pre-reveal access boundaries, mutation
  detection, pair orientation, schema/check integrity, and privacy-safe output.

### Interpretation boundaries

- The pipeline enforces procedural blinding but cannot prevent identity
  inference from response style or repeated content.
- The validator intentionally supports only the documented schema subset and
  rejects unknown assertion keywords.
- The completed v0.1 repeated-text report predates this automation and is not
  retroactively claimed as a v0.2 pipeline execution.

## v0.1.0 — 2026-09-08

First tagged public research preview.

### Included

- a local Ollama benchmark runner with per-run provenance and timing data;
- Track A model-capability tasks for German summarization, general knowledge,
  source-grounded writing, and coding;
- Track B agentic evaluations using a project-owned minimal harness and an
  exactly pinned Pi integration;
- deterministic coding and log-incident verifiers, blinded comparison bundles,
  and source-grounded quality rubrics;
- deployment catalogs, model lifecycle policy, resumable sweep controllers,
  and curated public-safe reports;
- synthetic incident fixtures and versioned task contracts;
- an Apache-2.0 license and an allowlisted, locally audited public release
  process.

### Interpretation boundaries

- This is an experimental research preview, not a universal model leaderboard.
- Results describe the tested model, quantization, runtime, harness, context,
  prompt, verifier, and hardware configuration together.
- Most published cells have one measured attempt and support capability mapping,
  not reliability distributions or latency-tail claims.
- Copyrighted source texts, personal writing inputs, raw model responses,
  trajectories, and private judge mappings are intentionally not distributed.
- The current Pi isolation boundary is macOS-specific and experimental.

See [README.md](README.md) for the project overview and
[PUBLICATION.md](PUBLICATION.md) for the public-content boundary.
