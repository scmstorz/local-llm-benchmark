# Interactive judge instructions

Version: `1.0.0`

These instructions govern an explicitly user-triggered Codex evaluation. The
local benchmark runner must not call a paid judge API.

## Inputs

Judge one comparison batch at a time. The bundle must contain:

- the exact cleaned source whose hash matches `source-metadata.json`
- `case.json`
- `benchmark-card.json`
- deterministic checks for every candidate
- candidate outputs under opaque randomized IDs

Do not inspect the mapping from candidate IDs to model names before all
individual and pairwise judgments are final.

## Procedure

1. Verify the case, card and source identifiers and versions.
2. Read the complete source and benchmark card before scoring candidates.
3. Evaluate every candidate independently against the source. Do not compare
   writing style across candidates during this pass.
4. For every key fact and key idea, assign exactly one status: `full`,
   `partial`, `missing` or `contradicted`. Provide a concise rationale and
   relevant source-location IDs.
5. Record every material error separately. Classify its severity as `critical`,
   `major` or `minor` and distinguish hallucination, contradiction,
   misattribution, numeric error, certainty inflation and other failure types.
6. Score the five judged dimensions using only the rubric anchors. Coverage
   points are derived mechanically from item statuses, not chosen freely.
7. Calculate the raw total, then apply hard-constraint and critical-error caps.
   Record every cap explicitly.
8. Select the verdict from the final score thresholds and return a result that
   validates against `judge-result.schema.json`.
9. After all independent results are frozen, perform an anonymized pairwise
   comparison only when final scores differ by at most three points or the
   ranking appears inconsistent with the written rationales. Randomize A/B
   order for that check.

## Grounding rules

- The cleaned source is the only factual authority for this evaluation.
- A correct external fact not present in the source is an unsupported addition,
  not bonus content.
- Preserve the distinction between benchmark design, measured baseline result,
  author interpretation or hypothesis, and acknowledged limitation.
- Do not turn task-completion rates into job-automation rates.
- Treat the reported values as results of the frozen model, agent scaffold and
  environment combinations, not timeless intrinsic properties of model names.
- The included main text is the complete source of truth for this case. Do not
  penalize candidates for omitting appendix-only details, and do not import such
  details from external knowledge.
- Source-location IDs support the judgment but must not be rewarded when copied
  into a candidate response.
- Treat the complete assistant content returned by Ollama as the candidate. Do
  not silently remove leaked `<think>` reasoning or repair an answer truncated
  at the configured token limit.
- Judge content before elegance. Fluent prose cannot compensate for a critical
  scope error or a confusion between full and partial completion.

## Reproducibility note

Record the available Codex model label, evaluation time, prompt version and
rubric version. Interactive Codex can change over time, so candidates intended
for direct comparison should be judged in the same batch. When adding a model
later, rejudge the full comparison set rather than treating an old score as a
permanent absolute measurement.

