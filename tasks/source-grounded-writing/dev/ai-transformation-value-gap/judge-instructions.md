# Interactive judge instructions

Version: `1.0.0`

These instructions govern an explicitly user-triggered Codex evaluation. The
local benchmark runner must not call a paid judge API.

## Inputs

Judge one comparison batch at a time. The bundle must contain:

- the exact source packet whose hash matches `source-metadata.json`;
- the exact three-thought user brief whose hash matches the same metadata;
- `case.json` and `benchmark-card.json`;
- deterministic checks for every candidate;
- candidate outputs under opaque randomized IDs.

Do not inspect the candidate-to-model mapping before all independent and
pairwise judgments are final.

## Procedure

1. Verify case, prompt, card and both candidate-input artifact versions and
   hashes.
2. Read all five source cards and all three personal thoughts before scoring.
3. Evaluate every candidate independently. Do not compare prose style across
   candidates during this pass.
4. For each evidence requirement `E01` through `E10`, assign `full`, `partial`,
   `missing` or `contradicted`. Cite the relevant `[Sxx]` locations.
5. For each personal thought `T01` through `T03`, use the same status scale.
   `Full` requires faithful, substantive integration into the argument; mere
   mention is at most `partial`.
6. Record material errors separately. Distinguish hallucination,
   contradiction, misattribution, numeric error, causal overclaim, scope
   inflation, certainty inflation and other failures.
7. Score the five judged dimensions using only the rubric anchors. Evidence and
   thought points are mechanically derived from assessment statuses.
8. Calculate the raw total, apply hard-constraint and critical-error caps, and
   return a result valid against `judge-result.schema.json`.
9. After all independent results are frozen, run a randomized anonymized
   pairwise check only when final scores differ by at most three points or the
   ranking conflicts with the written rationales.

## Grounding and synthesis rules

- The five source cards are the only authority for factual claims.
- The personal-thought file is authoritative only for the user's perspective;
  it is not empirical evidence.
- Correct external facts are unsupported additions, not bonus content.
- Do not require a mini-summary or explicit name-check of all five sources.
  Reward selective use when the resulting argument still covers the central
  evidence and its limitations.
- Distinguish time saved, task productivity, output quality, team effects,
  workflow redesign and enterprise financial value. They are not interchangeable.
- Treat McKinsey's EBIT results as self-reported associations, not audited
  causal estimates.
- Treat each experiment as evidence for its measured population, task, tool and
  period. Do not silently generalize to every company or occupation.
- Reward a post that relates sources across levels. Penalize a source-by-source
  list under `cross_source_synthesis`, even when each mini-summary is accurate.
- Treat the full assistant content returned by Ollama as the candidate. Do not
  remove leaked reasoning or repair truncation.

## Reproducibility note

Record the available Codex model label, evaluation time, prompt version and
rubric version. Interactive Codex can change over time, so candidates intended
for direct comparison must be judged in the same batch. A later challenger
requires rejudging the complete candidate set.

