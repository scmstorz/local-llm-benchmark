# Agentic software development and the reality gap

Case ID: `source_grounded_writing.dev.agentic-software-development-reality-gap`

This is the second development case in the source-grounded writing track. It
asks a model to create a German LinkedIn post from five English-language
evidence cards and exactly three personal thoughts from the user.

## Current state

The five-source evidence packet, three user-approved thoughts, provenance
metadata, prompt, 100-point scoring rubric, judge contract and executable
`case.json` are frozen. The source papers and personal-thought artifact are
hash-verified local inputs excluded from Git. The frozen five-model comparison
is complete: all ten requests completed technically, four warm candidates are
complete German posts and one is an empty length-terminated quality failure.
Execution integrity is recorded in the
[`execution report`](../../../../reports/source-grounded-writing/agentic-software-development-reality-gap-execution.md).
The joint judgment is also complete. Ornith leads at 83, followed by Qwen 3.8
at 81, Qwen 3.6 at 63.5, Muse Glimmer at a critical-error-capped 59 and invalid
GPT-OSS at zero. Ornith is the sole observed quality-latency Pareto deployment.
The complete scoring rationale, pairwise check and blinding limitation are
recorded in the
[`quality report`](../../../../reports/source-grounded-writing/agentic-software-development-reality-gap-quality.md).

## Why this is the next controlled case

The first source-grounded case varied both evidence and user perspective while
holding the requested artifact constant: a 400-550 word German LinkedIn post.
This case keeps that output form so the comparison primarily tests topic and
evidence transfer rather than a new genre.

The packet is deliberately heterogeneous. It combines:

1. an economically grounded autonomous-agent benchmark;
2. an agent-interface ablation study;
3. a multi-model study of task-completion horizons;
4. a randomized trial of experienced developers using AI; and
5. an observational study of team and organizational conditions.

These sources do not answer the same question. Their disagreement and
different units of analysis are part of the writing task.

## Why this is not a summarization case

[`source-packet.md`](source-packet.md) contains five visibly separate evidence
cards and 25 atomic facts or boundaries. There are deliberately:

- no transitions between sources;
- no overall thesis;
- no recommended ordering;
- no supplied reconciliation of benchmark and field evidence;
- no integration of the user's frozen position.

The candidate must select evidence, distinguish autonomous agents from
human-assistance tools, connect capability to verified outcomes and create an
original argument for a professional audience.

## Selected sources

1. *SWE-Lancer*
2. *SWE-agent*
3. *Measuring AI Ability to Complete Long Software Tasks*
4. *Measuring the Impact of Early-2025 AI on Experienced Open-Source Developer
   Productivity*
5. *DORA 2025 State of AI-assisted Software Development Report*

## Execution contract

- target language: German
- target form: one LinkedIn post
- target length: 400-550 words
- hard maximum: 600 words
- candidate browsing and tools: disabled
- context window: at least 8,192 tokens
- quality candidate: one warm run in the Capability Sweep
- evaluation: deterministic compliance checks followed by a blinded,
  source-grounded interactive Codex judgment

The prompt, ten weighted evidence requirements and known-error taxonomy were
written only after the user approved the three-thought consolidation. The case
is included in the immutable capability-suite v0.3 manifest. The five-model
[`comparison plan`](comparison-plan.json) freezes exact deployment digests,
the counterbalanced `AEDBC` order and the resource gate before candidate
generation. The completed comparison followed that plan unchanged.
