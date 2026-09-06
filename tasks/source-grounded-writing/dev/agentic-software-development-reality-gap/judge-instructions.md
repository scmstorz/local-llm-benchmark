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
- Distinguish autonomous-agent task success, human-AI productivity, model-plus-
  scaffold capability, organizational associations and production reliability.
  They are not interchangeable.
- Treat the SWE-Lancer and SWE-agent scores as historical results for their
  stated model, scaffold, dataset and verifier configurations, not as current
  model rankings.
- A 50-percent task-completion horizon is not a dependable autonomy horizon;
  preserve the substantially shorter 80-percent horizon and the missing
  high-reliability estimate.
- Treat the experienced-developer result as causal for its randomized setting,
  not as a universal claim about developers or coding agents.
- Treat DORA's adjusted relationships as observational and its productivity
  figures as perceptions, not direct telemetry or randomized effects.
- Reward a post that explains why benchmark progress and a field-study slowdown
  can coexist. Penalize a source-by-source list under `cross_source_synthesis`,
  even when each mini-summary is accurate.
- The user's position supports broad delegation only with risk-, complexity-
  and verifier-dependent control. Do not mistake it for evidence that research
  has established universal production readiness.
- Treat the full assistant content returned by Ollama as the candidate. Do not
  remove leaked reasoning or repair truncation.

## Reproducibility note

Record the available Codex model label, evaluation time, prompt version and
rubric version. Interactive Codex can change over time, so candidates intended
for direct comparison must be judged in the same batch. A later challenger
requires rejudging the complete candidate set.
