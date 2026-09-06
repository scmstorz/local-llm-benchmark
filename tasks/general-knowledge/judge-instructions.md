# Interactive judge instructions

Version: `1.0.0`

These instructions govern an explicitly user-triggered Codex evaluation. The
local benchmark runner must not call a paid judge API.

## Inputs

Judge one comparison batch at a time. The bundle must contain the case, exact
reference dossier, benchmark card, deterministic checks and candidate outputs
under opaque randomized IDs.

Do not inspect the mapping from candidate IDs to model names before all
individual and any required pairwise judgments are final.

## Procedure

1. Verify the case, card and reference identifiers and versions.
2. Read the complete reference dossier and benchmark card before scoring.
3. Evaluate each candidate independently. Do not compare prose style during
   this pass.
4. For every key fact and key idea, assign exactly one status: `full`,
   `partial`, `missing` or `contradicted`. Cite the reference-location IDs that
   support the assessment.
5. Record every material error separately and classify its severity and type.
6. Score the five judged dimensions from the rubric anchors. Coverage points
   are derived mechanically from item statuses.
7. Calculate the raw total and apply all hard-constraint and critical-error
   caps explicitly.
8. Return a result that validates against `judge-result.schema.json`.
9. After independent results are frozen, use an anonymized pairwise check only
   if scores differ by at most three points or the ranking conflicts with the
   rationales.

## Grounding rules

- The dossier is the factual authority for scoring, not an input that the
  candidate was expected to quote.
- Reward correct explanations expressed in the candidate's own words.
- Do not reward unsupported extra detail merely because it sounds plausible.
- A harmless correct detail outside the dossier is not automatically an error,
  but it earns no coverage credit. Material unverifiable claims reduce factual
  accuracy.
- Judge whether the answer addresses the actual question, not whether it
  resembles the dossier's organization.
- Preserve important conditions and distinctions. Fluent prose cannot
  compensate for a central misconception or false certainty.
- Treat the complete Ollama assistant content as the candidate. Do not repair
  truncated answers or remove leaked reasoning.

## Reproducibility note

Record the available Codex model label, evaluation time, prompt version and
rubric version. Interactive Codex can change over time, so candidates intended
for direct comparison should be judged in the same batch. When adding a model
later, rejudge the complete comparison set.

