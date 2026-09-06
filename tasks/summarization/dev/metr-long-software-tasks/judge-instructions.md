# Interactive judge instructions

Version: `1.0.0`

These instructions govern an explicitly user-triggered Codex evaluation. The
local benchmark runner must not call a paid judge API.

## Inputs

Judge one comparison batch at a time. The bundle must contain:

- the exact extracted source whose hash matches `source-metadata.json`
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

- The extracted source is the only factual authority for this evaluation.
- A correct external fact not present in the source is an unsupported addition,
  not bonus content.
- Preserve the distinction between metric definition, experimental method,
  measured result, qualitative interpretation and conditional extrapolation.
- Time horizon is indexed to a success probability, task distribution, domain
  and reference human population; it is not a context-free model property.
- Treat results as properties of the evaluated model-and-scaffold agent systems,
  not intrinsic model scores.
- Do not turn the one-month software-task extrapolation into a demonstrated AGI
  date, a job-automation date or an unconditional forecast.
- Do not punish a candidate for using either 169 or 170 as the approximate task
  total, or 11 versus 12 frontier models, because the frozen main paper itself
  uses both counts in closely related passages. Reward the stable composition
  and method instead.
- The included main text is the complete source of truth. Do not penalize
  candidates for omitting appendix-only details and do not import such details.
- Treat the complete assistant content returned by Ollama as the candidate. Do
  not silently remove leaked `<think>` reasoning or repair an answer truncated
  at the configured token limit.
- Judge content before elegance. Fluent prose cannot compensate for certainty
  inflation or confusion between 50% reliability and dependable automation.

## Reproducibility note

Record the available Codex model label, evaluation time, prompt version and
rubric version. Interactive Codex can change over time, so candidates intended
for direct comparison should be judged in the same batch. When adding a model
later, rejudge the full comparison set rather than treating an old score as a
permanent absolute measurement.
