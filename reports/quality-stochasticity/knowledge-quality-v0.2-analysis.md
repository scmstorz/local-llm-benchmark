# General-Knowledge Quality Stochasticity v0.2 — Interpretation

This companion analysis interprets the immutable, pipeline-generated
[aggregate](knowledge-quality-v0.2.md). It does not replace or modify that
artifact. The study used five fresh generations for each of two deployments
on each of two frozen difficult-knowledge cases.

## Result at a glance

| Case | Model | Mean | Median | Sample SD | Range | Pair W-L-T | Unique | Median wall time | Median first content |
| --- | --- | ---: | ---: | ---: | --- | --- | ---: | ---: | ---: |
| Medical screening and Bayes | Muse Glimmer | 88.10 | 92.00 | 6.80 | 80–94.5 | 2-3-0 | 5/5 | 27.06 s | 7.74 s |
| Medical screening and Bayes | Qwen 3.8 | 92.00 | 92.50 | 1.12 | 90–92.5 | 3-2-0 | 2/5 | 29.20 s | 1.77 s |
| ML evaluation leakage | Muse Glimmer | 92.20 | 94.00 | 4.02 | 85.5–95.5 | 3-2-0 | 5/5 | 30.58 s | 4.01 s |
| ML evaluation leakage | Qwen 3.8 | 92.20 | 92.50 | 0.67 | 91.5–93 | 2-3-0 | 3/5 | 29.27 s | 1.93 s |

All 20 runs completed technically, passed the deterministic output checks and
produced a usable answer. Qwen received an `excellent` verdict in all ten
judgments. Glimmer received seven `excellent` and three `good` verdicts.

## What the repetitions changed

The earlier one-answer comparison favored Glimmer on both cases. Repetition
does not support turning that observation into a stable cross-case advantage.
The ten direct same-repetition comparisons split 5–5, while the combined
descriptive means were 92.10 for Qwen and 90.15 for Glimmer.

Qwen's main advantage was its quality floor. Across both cases, its ten scores
remained between 90 and 93. By contrast, Glimmer reached the two highest
individual scores in the study but
also fell to 80 and 81.5 on the Bayes case and 85.5 on ML leakage. This is the
practical distinction between consistently excellent output and higher-upside
but less predictable output.

The most consequential variation occurred in two Glimmer Bayes answers. They
contradicted the source-supported screening mechanism by reversing or
misstating the role of lead time. Qwen's Bayes answers contained only minor
issues. On ML leakage, Glimmer won three of five direct pairs and produced the
best individual answer, but its lowest answer underspecified the final
hyperparameter-selection procedure. Qwen remained in a narrow 91.5–93 band.

## Operational interpretation

For these two difficult knowledge tasks under the frozen settings, Qwen 3.8 is
the safer default when a reliably strong first answer matters. It also started
visible output sooner and decoded faster. Glimmer remains interesting as a
quality-first challenger when its higher upside is worth additional factual or
methodological verification. This is a task-bound routing observation, not a
general ranking of the model families.

The similar median wall times do not contradict Qwen's faster first-content
and decode measurements: natural answers differed in length, and this was a
quality study rather than a controlled fixed-token performance benchmark. One
65.75-second Glimmer ML observation widened its wall-time range, but five
samples do not support a tail-latency claim.

## Interpretation boundaries

- Five observations per cell are exploratory. They reveal material variation
  but do not estimate rare-event probabilities or P90/P95/P99 latency.
- Temperature zero and a fixed seed did not make either deployment universally
  byte-deterministic. Glimmer produced 10/10 unique outputs; Qwen produced two
  unique Bayes outputs and three unique ML outputs.
- A recurring error *type* is a broad taxonomy count, not proof that the exact
  same semantic error recurred. Exact recurrence is claimed above only where
  the judgment descriptions support it.
- The interactive judge followed the anonymized scalar-then-pairwise pipeline,
  and mappings remained closed until both freezes existed. Observable response
  identity and bundle metadata mean the process is procedurally blinded, not a
  claim of guaranteed cognitive blindness.
- Scores use separate case-specific 0–100 rubrics. Their arithmetic combination
  is descriptive and is not a universal composite benchmark score.

## Provenance

- Study checkpoint: `quality-study-20260909T152526Z-090c25b9`
- Frozen plan SHA-256:
  `c0fddc2e89b0da46d74029c1e473fb4587ede1edd4902fc70c07194fa37fa686`
- Scalar judgment freeze:
  `6349b889f68bed77e75dee1350341636bd28606b5c50874701ebf1567e905885`
- Pairwise judgment freeze:
  `6ab5b6a5f9e511860d63788b389bb48d17220e204594c653a2e8fcb26e500816`
