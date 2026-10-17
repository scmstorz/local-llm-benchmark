# Multi-Format Document Analysis v0.1

This document defines the first read-only multi-format benchmark case. The
semantic contract is implemented and tested. The DOCX and XLSX sources are
qualified, as is the PDF source. The common canonical extraction is also
qualified. The shared artifact backend and the complete Mini and pinned-Pi
surfaces are qualified. The excluded Mini v0.1 and corrected Pi v0.3 smokes
both passed all 11 semantic checks. The separately authorized measured Track
A/Track B sweep and its supplemental prose review are complete.

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

The DOCX, PDF and XLSX bytes now exist and are frozen after format-specific
structural, extraction and visual checks. The blueprint is not a
candidate-facing canonical extraction and must not be used as a measured input.
The separate canonical representation contains 15 source-derived evidence
records with stable fact codes, exact anchors, raw text and typed values or
formulas. It does not contain the controlled decision, blockers or actions.

## Qualified read-only tool surface

The harness exposes four format-specific operations instead of a shell:

- `list_artifacts` returns names, formats, sizes and frozen hashes;
- `read_docx` reads the admitted paragraphs or table through stable anchors;
- `read_pdf` reads the admitted page text or tables through stable anchors;
- `read_xlsx` reads the admitted sheet regions with values, formulas and
  cached displayed values.

Every response is bounded to 8,192 bytes and every call is audited. The backend
requires exactly the three frozen artifacts, rejects symlinks and verifies the
binary hash before every read. DOCX and XLSX use standard-library OOXML
extraction; PDF uses the exact resolved Poppler `pdftotext` executable. Its 15
binary-derived records match the frozen canonical extraction exactly, but the
candidate path never loads the canonical file or hidden reference.

Mini and Pi copy the same backend bytes into their run directories. Pi is
pinned to 0.84.4, starts with built-in tools disabled and registers only the
four operations above. Its macOS Seatbelt policy prevents artifact writes and
hidden-reference access, and allows network only to loopback Ollama. Real
acceptance exposed that Homebrew's Python framework launcher spawns a separate
`Python.app` worker. Pi v0.3 therefore executes that exact worker directly and
allows only it, exact Node and exact `pdftotext`. Its expanded 12-check
pre-inference acceptance also loads the explicit extension and policy beneath
Seatbelt; the final smoke passed that check. OpenCode is not admitted merely
because it has a qualification card elsewhere in the project.

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
- explicit no-inference qualification record;
- `regional-readiness.xlsx` authored under the explicit XLSX runtime amendment;
- all XLSX formulas and cached values structurally checked;
- both XLSX worksheets rendered and visually inspected;
- XLSX source anchors, binary hash and runtime versions frozen;
- `rollout-policy.docx` authored under the explicit DOCX runtime amendment;
- DOCX preset tokens, headings, bookmarks, numbering and table geometry checked;
- both DOCX pages rendered and visually inspected;
- DOCX source anchors, binary hash and runtime versions frozen;
- `reliability-review.pdf` authored under the explicit ReportLab amendment;
- PDF page geometry, metadata, outline and safety properties checked;
- preliminary, final and material-change tables extracted exactly;
- all three PDF pages rendered and visually inspected;
- PDF source anchors, binary hash and runtime versions frozen;
- canonical extraction schema and 15-record representation frozen;
- fresh extraction from all three binaries matches the frozen JSON exactly;
- all fact codes and source anchors match the blueprint in order;
- controlled decision, blocker and action leakage scan passed.
- shared bounded artifact backend and exact three-file inventory qualified;
- all 15 backend records match the frozen canonical records in order;
- Mini action loop, persistent interruption state and complete audit qualified;
- pinned Pi custom-tool surface, built-in-tool exclusion and policy auditing
  qualified;
- no-inference isolation and orchestration regressions passed;
- Mini v0.1 excluded smoke completed with strict transport, no tool errors and
  11/11 semantic checks;
- Pi v0.1 Seatbelt process-identity failure preserved before Pi or inference;
- Pi v0.2 extension-identity failure preserved with zero turns, tokens and
  tool calls;
- Pi v0.3 admitted as a distinct corrected system after a real 12/12 Seatbelt
  and explicit-extension acceptance;
- Pi v0.3 excluded smoke completed without tool errors and with 11/11 semantic
  checks; surrounding text required deterministic normalization, so strict
  transport remains false;
- Qwen unloaded after each executed system and final Ollama postflight empty.

Completed measured boundary:

- independent post-freeze authorization bound to the frozen plan hash;
- all 15 measured cells executed exactly once without retry;
- all 15 fresh resource gates and all five 12-check Pi Seatbelt acceptances
  passed;
- deterministic result: 2/15 semantic successes, 12/15 strict transports and
  114/165 essential checks;
- supplemental result: 7/13 parseable reports pass the prose review, and both
  deterministic successes pass it;
- final Ollama postflight empty.

Completed targeted-confirmation boundary:

- separate post-freeze authorization bound to the exact nine-cell Qwen 3.8
  plan hash;
- all nine fresh cells completed exactly once, without retry or historical-cell
  reuse;
- all nine resource gates and all three fresh 12-check Pi Seatbelt acceptances
  passed;
- deterministic result: 5/9 semantic successes, 6/9 strict transports and
  79/99 essential checks;
- supplemental result: 6/9 reports pass prose review and all five deterministic
  successes pass it;
- final Ollama postflight empty.

The measured plan crosses the five active-default deployments with three
conditions: one tool-free canonical Track A request, Mini v0.1 over the real
artifacts and Pi v0.3 over the same artifacts. Every exact cell has one attempt,
automatic retries are zero and qualification smokes are not reused. The order
cycles the three conditions without adjacent use of the same model. Track A
and Track B remain separate in every aggregate. The plan SHA-256 is
`822074b8abfe631bf7c1f63dcdcc03af24d81a7dd3a260722ceec4a485b26389`.

The final Phase 95 regression passes 545 Python tests and the dependency-free
public registry passes 381 tests in the worktree. The default Pi Node suite
passes 17 active tests with one expected opt-in transport skip, and the two
direct multi-format policy files pass 7/7. These regression checks do not
contact Ollama; live outcomes are reported separately above.

The measured study is
`multi-format-capability-20260911T063427Z-0069dc6c`. Track A records 0/5
semantic successes, Mini records 1/5 and Pi records 1/5. The two successful
cells both use Qwen 3.8, at positions 8 and 12, and both also pass strict
transport and the supplemental review. These n=1 observations do not establish
a universal model ranking, a reliability rate, a latency distribution or a
one-factor Mini-versus-Pi effect.

## Targeted Qwen 3.8 confirmation

The follow-up was separately frozen rather than retrofitted onto the capability
sweep, then authorized by an immutable artifact bound to plan SHA-256
`31cb64238d854226fd1937310c3409a5a64fd6e46275b33e067352d9315a7858`.
Study `multi-format-qwen38-confirmation-20260911T185719Z-086e9a45` executed the
balanced order `A-Mini-Pi / Mini-Pi-A / Pi-A-Mini` with unchanged inference
controls. It reused no historical observation, made no retry and completed all
nine cells with valid termination and a parseable report.

Mini reproduced the full semantic result in 3/3 attempts, used strict transport
in all three and passed 33/33 checks. Pi passed semantics in 2/3 and 22/33
checks, but all three outputs required surrounding-text normalization. The
third Pi report was materially correct in the separate prose review, yet
remains a real deterministic 0/11 failure because it emitted schema version
`1.0` instead of the required `1.0.0`. Canonical Track A used strict transport
in 3/3 but passed only 24/33 checks: all three byte-identical reports approved
West despite citing 94% completion against the required 95% gate and omitted
West from the blocked regions.

The separate non-blinded prose audit accepts 6/9 reports. Combined
deterministic, prose and strict acceptance is 3/9, all under Mini. The initial
resource check paused before inference when two unrelated models remained
loaded; both were explicitly unloaded and the same unconsumed cell resumed.
Every subsequent gate passed, every Pi cell passed a fresh 12/12 Seatbelt
acceptance, Qwen was unloaded after each cell and the final Ollama postflight
was empty. These three observations per condition describe bounded consistency,
not population reliability, latency distributions or a universal ranking.

The machine-readable entry points are the
[case](../tasks/agentic/multi-format-document-analysis/rollout-readiness-reconciliation/case-v0.1.json),
[source blueprint](../tasks/agentic/multi-format-document-analysis/rollout-readiness-reconciliation/source-blueprint-v0.1.json),
[DOCX authoring amendment](../tasks/agentic/multi-format-document-analysis/rollout-readiness-reconciliation/docx-authoring-amendment-v0.1.json),
[DOCX qualification](../tasks/agentic/multi-format-document-analysis/rollout-readiness-reconciliation/docx-artifact-qualification-v0.1.json),
[PDF authoring amendment](../tasks/agentic/multi-format-document-analysis/rollout-readiness-reconciliation/pdf-authoring-amendment-v0.1.json),
[PDF qualification](../tasks/agentic/multi-format-document-analysis/rollout-readiness-reconciliation/pdf-artifact-qualification-v0.1.json),
[canonical extraction schema](../tasks/agentic/multi-format-document-analysis/canonical-extraction-schema-v1.json),
[canonical extraction](../tasks/agentic/multi-format-document-analysis/rollout-readiness-reconciliation/canonical/canonical-extraction-v0.1.json),
[canonical extraction qualification](../tasks/agentic/multi-format-document-analysis/rollout-readiness-reconciliation/canonical-extraction-qualification-v0.1.json),
[XLSX authoring amendment](../tasks/agentic/multi-format-document-analysis/rollout-readiness-reconciliation/xlsx-authoring-amendment-v0.1.json),
[XLSX qualification](../tasks/agentic/multi-format-document-analysis/rollout-readiness-reconciliation/xlsx-artifact-qualification-v0.1.json),
[shared artifact API qualification](../tasks/agentic/track-b/multi-format-artifact-api-v0.1-qualification.json),
[Mini qualification](../tasks/agentic/track-b/mini-multi-format-v0.1-qualification.json),
[Pi v0.3 qualification](../tasks/agentic/track-b/pi-multi-format-v0.3-qualification.json),
[frozen original smoke pair](../tasks/agentic/track-b/multi-format-qualification-smokes-v0.1.json),
[completed smoke report](../reports/agentic/multi-format-qualification-smokes-v0.1.md),
[Track A qualification](../tasks/agentic/track-a/multi-format-canonical-v0.1-qualification.json),
[controller qualification](../tasks/agentic/multi-format-capability-sweep-v0.1-controller-qualification.json),
[frozen measured plan](../tasks/agentic/multi-format-capability-sweep-v0.1.json),
[deterministic measured report](../reports/agentic/multi-format-capability-sweep-v0.1.md),
[supplemental quality audit](../reports/agentic/multi-format-capability-sweep-v0.1-quality-audit.md),
[targeted confirmation controller qualification](../tasks/agentic/multi-format-qwen38-confirmation-v0.1-controller-qualification.json),
[frozen targeted confirmation plan](../tasks/agentic/multi-format-qwen38-confirmation-v0.1.json),
[targeted execution authorization](../tasks/agentic/multi-format-qwen38-confirmation-v0.1-execution-authorization.json),
[targeted deterministic report](../reports/agentic/multi-format-qwen38-confirmation-v0.1.md),
[targeted quality audit](../reports/agentic/multi-format-qwen38-confirmation-v0.1-quality-audit.md)
and [overall qualification record](../tasks/agentic/multi-format-document-analysis/multi-format-v0.1-offline-qualification.json).

The separately versioned successor is the
[non-isomorphic supplier-award transfer case](multi-format-transfer-v0.2.md).
Its semantic contract is qualified, but its binary artifacts and any live
execution remain behind independent Phase 96 gates.
