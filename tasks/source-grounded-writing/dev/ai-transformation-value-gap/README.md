# AI transformation and the enterprise value gap

Case ID: `source_grounded_writing.dev.ai-transformation-value-gap`

This is the first development case in the source-grounded writing track. It
asks a model to create a German LinkedIn post from five English-language
evidence cards and exactly three personal thoughts from the user.

## Current state

The evidence packet, three user-authored thoughts, provenance metadata, prompt,
scoring rubric and executable `case.json` are frozen. The private thought file
is hash-verified but excluded from Git. The controlled five-model comparison is
complete; execution integrity is recorded in the
[`execution report`](../../../../reports/source-grounded-writing/ai-transformation-value-gap-execution.md),
and the completed judgment in the
[`quality report`](../../../../reports/source-grounded-writing/ai-transformation-value-gap-quality.md).

## Why this is not a summarization case

The candidate does not receive a project-authored article or a unified source
narrative. [`source-packet.md`](source-packet.md) contains five visibly separate
evidence cards. Each card consists of atomic notes about one publication's
method, findings and limitations. There are deliberately:

- no transitions between sources;
- no overall thesis;
- no recommended ordering of evidence;
- no ready-made conclusion;
- no integration of the user's position.

The candidate must decide which evidence matters, relate findings produced at
different levels of analysis, incorporate the three personal thoughts and
create an original argument for a professional audience.

## Selected sources

1. McKinsey's 2025 global AI survey
2. *Generative AI at Work*
3. *Navigating the Jagged Technological Frontier*
4. *The Cybernetic Teammate*
5. *Shifting Work Patterns with Generative AI*

Together they cover organizational self-reports, operational deployment data
and randomized experiments at individual, task, team and multi-firm levels.
Their differences are part of the task rather than noise to be smoothed away.

## Intended execution contract

- target language: German
- target form: one LinkedIn post
- target length: 400–550 words
- hard maximum: 600 words
- candidate browsing and tools: disabled
- context window: at least 8,192 tokens
- quality candidate: one warm run in the Capability Sweep
- evaluation: deterministic compliance checks followed by a blinded,
  source-grounded interactive Codex judgment

The runner now supports independently hashed source and personal-thought
artifacts. They will remain separate in the prompt template and judge bundle.
The first five-model execution order and fixed settings are frozen in
[`comparison-plan.json`](comparison-plan.json) before any candidate generation.
