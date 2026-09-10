# Multi-Format Document Analysis v0.1

This document defines the first read-only multi-format benchmark case. The
semantic contract is implemented and tested; the binary artifacts and artifact
harness are not yet qualified. No model inference is authorized by this design.

## Decision question

Can a local model or complete agent system reconcile policy, validation and
capacity evidence across Word, PDF and Excel well enough to make a verified
regional rollout decision?

The synthetic development case is
`agentic.documents.rollout-readiness-reconciliation`. A governance memo defines
four mandatory region-level gates and permits a phased launch when at least one
region passes. A reliability review contains preliminary and superseding final
regional evidence. A workbook contains capacity inputs, formula-derived ratios
and a misleading aggregate `GO` dashboard.

The correct controlled outcome is a phased launch for North only. Central has
too many open Sev-2 issues, West misses the completion threshold and East has
an open Sev-1 issue. The portfolio dashboard cannot override the region-level
policy, and the PDF's final table supersedes its preliminary table.

## Why this is not one opaque office benchmark

The case defines two separate experimental conditions:

1. **Canonical representation / Track A.** Every model receives the same
   frozen extracted representation. This asks whether the model can perform the
   cross-source reasoning when artifact extraction is held constant.
2. **Real artifact harness / Track B.** The complete system must discover and
   extract evidence from the real `.docx`, `.pdf` and `.xlsx` files through a
   frozen read-only tool surface. Artifact libraries and extraction behavior
   are part of the system identity.

Results from these conditions must not be pooled. A failure in Track B can be
caused by model reasoning, tool selection, extraction or the harness contract;
the paired canonical condition helps localize the boundary without pretending
to isolate every causal component.

OCR, arbitrary PDF editing, Word report generation and spreadsheet repair are
not measured here. Vision-native OCR and common-OCR-plus-LLM systems remain a
future study with their own comparison identity.

## Planned artifacts

The project-authored source blueprint defines three synthetic artifacts:

- `rollout-policy.docx`: a business memo with a real gate table, region-level
  decision rule, phased-release rule and evidence cutoff;
- `reliability-review.pdf`: a paginated review whose final table explicitly
  supersedes a plausible preliminary table;
- `regional-readiness.xlsx`: separate Summary and Capacity sheets with typed
  inputs, auditable ratio formulas and an intentionally incorrect aggregate
  business rule on the dashboard.

The artifact bytes do not yet exist. The blueprint is not a candidate-facing
canonical extraction and must not be used as a measured input.

## Planned read-only tool surface

The harness should expose format-specific operations instead of a shell:

- list artifact names, formats and basic metadata;
- read Word paragraphs and tables with stable semantic anchors;
- read selected PDF pages or tables with stable page anchors;
- inspect selected workbook ranges with values, formulas, displayed values and
  sheet visibility;
- return bounded responses and record every tool call.

No operation may modify an artifact, contact the network, inspect unrelated
repository paths or reveal the hidden reference. Mini and Pi must receive
equivalent capabilities before any system comparison. OpenCode is not admitted
merely because it has a qualification card elsewhere in the project.

## Output and verification

The candidate returns one strict structured decision report. Eleven
deterministic checks cover:

- JSON schema;
- overall decision;
- approved regions;
- decisive blocker per held region;
- exact fact-to-source-anchor integrity;
- required evidence coverage;
- evidence from all three formats;
- both source conflicts and their resolution;
- minimum action plan;
- explicit uncertainties;
- controlled-value integrity.

The verifier does not infer whether arbitrary German prose is negated,
misleading or well written. A supplemental human or fixed-LLM review remains
required for free-text claim polarity, wording accuracy, calibration and
executive usefulness. Deterministic success and strict JSON transport remain
separate outcomes; there is no composite score.

## Qualification sequence

Although the final task uses three formats, artifact capability is admitted one
family at a time:

1. create and qualify the XLSX artifact, formulas, renders and extraction;
2. create and qualify the DOCX artifact, OOXML structure, renders and
   extraction;
3. create and qualify the PDF artifact, page renders, text/table extraction and
   source anchors;
4. freeze hashes and reconcile every canonical fact against the visually
   inspected binary source;
5. qualify the combined read-only Mini surface, then the pinned Pi surface;
6. run one excluded smoke per admitted complete system;
7. freeze a small measured capability plan only after all prior gates pass.

This order preserves the roadmap's cross-format guardrail. The final combined
case cannot hide an unqualified per-format extractor behind apparently correct
model output.

## Current gate status

Complete:

- decision question and synthetic fact design;
- source blueprint and stable planned anchors;
- strict report schema and visible codebooks;
- hidden controlled ground truth and reference report;
- deterministic verifier and targeted near-miss tests;
- Track A/Track B evidence boundary;
- explicit no-inference qualification record.

Pending:

- all three binary artifact bytes;
- visual and structural artifact QA;
- canonical extraction and parity audit;
- artifact tool surface and isolation qualification;
- excluded Mini and Pi smokes;
- measured plan and execution authorization.

The machine-readable entry points are the
[case](../tasks/agentic/multi-format-document-analysis/rollout-readiness-reconciliation/case-v0.1.json),
[source blueprint](../tasks/agentic/multi-format-document-analysis/rollout-readiness-reconciliation/source-blueprint-v0.1.json)
and [qualification record](../tasks/agentic/multi-format-document-analysis/multi-format-v0.1-offline-qualification.json).
