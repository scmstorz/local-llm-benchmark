# Multi-Format Document Analysis

This task family evaluates evidence reconciliation across real office-document
formats. It keeps two conditions separate:

- Track A reasons over one frozen canonical extraction;
- Track B evaluates a complete system using a frozen read-only artifact tool
  surface.

The first development case is
`agentic.documents.rollout-readiness-reconciliation`. Its semantic contract and
verifier are implemented, but the `.docx`, `.pdf` and `.xlsx` artifacts do not
yet exist and no harness is qualified. The machine-readable qualification
record therefore prohibits a live run.

OCR, arbitrary document editing, Word report assembly and spreadsheet repair
are separate future tasks. A result in this family must not be used as evidence
for those capabilities.
