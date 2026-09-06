# METR long-software-tasks - development case

Case ID: `summarization.dev.metr-long-software-tasks`

This is the third summarization development case and the second research-paper
case. It tests whether a local model can turn an English empirical paper into a
clear, source-faithful German summary for an informed non-specialist reader.

The case is classified as `hard`. It combines a new metric, mixed task suites,
human baselines, logistic modeling, historical trend estimation, qualitative
failure analysis, external-validity checks and explicitly conditional forecasts.
An attractive but weak response can easily turn a software-task extrapolation
into a general or certain prediction.

## Frozen source scope

The input is the final paper *Measuring AI Ability to Complete Long Software
Tasks*, published in the NeurIPS 2025 Main Conference Track. The official PDF
has 54 pages. The executable source includes the ten-page main paper through
Section 6, including material captions, tables, formulas and footnotes. It
excludes acknowledgments, references, appendices A through K and the NeurIPS
checklist.

This boundary keeps the case focused on summarizing the complete main argument.
The large appendices remain available privately for verification and a possible
future long-context experiment. They are not silently used by either candidate
models or the interactive judge.

The published main paper itself contains minor count inconsistencies: closely
related passages refer to both 169 and 170 tasks and to both 11 and 12 frontier
models. The executable source preserves these rather than inventing a correction;
the rubric does not make either count a decisive quality criterion.

## Private source

The source artifacts are stored under:

```text
data/private/summarization/dev/metr-long-software-tasks/
```

They remain Git-ignored. `source-metadata.json` freezes the official publication,
scope, extraction process and SHA-256 hashes. Stable `[P01]` through `[P19]`
location labels support judge evidence only and must not appear in candidate
outputs.

## Context requirement

This case requires at least a 16,384-token context window. The runner rejects a
smaller configured context before contacting Ollama.

Run one model without a warm-up:

```bash
python3 -m local_llm_benchmark run \
  --model qwen3.6:35b-a3b-mxfp8 \
  --case tasks/summarization/dev/metr-long-software-tasks/case.json \
  --num-ctx 16384
```

Before a performance comparison, follow the mandatory application-stop and
Ollama preflight gate in `PROJECT_STATUS.md`.
