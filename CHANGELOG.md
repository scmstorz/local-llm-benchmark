# Changelog

Repository releases use project-level versions. Task, dataset, prompt, verifier,
harness, and study-protocol versions are independent immutable identifiers. A
task named `v0.5` therefore does not imply project release `v0.5.0`.

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
