# Ornith 1.5 35B Challenger Sweep — Execution Report

Date: 2026-08-29  
Sweep: `sweep-20260829T100955Z-f96e5d8b`  
Harness commit: `281ddd33646d6705d73d3380c9071fffe9593232`  
Status: execution complete; all thirteen cases jointly rejudged

## Deployment

- Ollama name: `ornith-1.5:35b`
- digest: `9f3b89b2521908dd2e6f7a11fa368e62c8f89e1075f22604e4d1a76dd1240fcc`
- architecture family: `qwen35moe`
- parameters: 35.5B
- quantization: `Q4_K_M`
- artifact size: 22,616,285,024 bytes
- declared context length: 262,144 tokens
- Ollama: 0.32.15
- generation: temperature 0, seed 42, thinking disabled, 2,600-token maximum

The three summarization cases used their declared context sizes: 8,192 tokens
for the MIT Sloan article and 16,384 for both research papers. All general
knowledge cases used 8,192 tokens.

## Execution outcome

- 13 of 13 cases completed
- 26 of 26 cold and warm generations completed with `done_reason=stop`
- all 26 generations passed the deterministic language, length, structure,
  reasoning-markup and source-label checks
- 13 warm quality candidates were preserved
- 260 judge-bundle artifact hashes were verified
- no timeout, runtime failure, OOM or unrelated Ollama model was observed
- Ollama was empty before the preflight window and remained empty after the
  postflight window
- every cold/warm response pair was byte-identical

Byte identity is an execution observation, not a quality result. It shows that
this deployment reproduced the exact visible response for all 13 cases under
the fixed temperature and seed condition.

## Warm screening measurements

| Position | Case | Wall time | Output speed | Words | Complete |
| ---: | --- | ---: | ---: | ---: | --- |
| 1 | `summarization.dev.mit-sloan-ai-climate` | 11.46 s | 86.59 tok/s | 540 | yes |
| 2 | `summarization.dev.the-agent-company` | 17.46 s | 82.89 tok/s | 836 | yes |
| 3 | `summarization.dev.metr-long-software-tasks` | 22.14 s | 83.80 tok/s | 962 | yes |
| 4 | `general_knowledge.dev.confidence-intervals` | 12.70 s | 88.55 tok/s | 585 | yes |
| 5 | `general_knowledge.dev.confidence-intervals-transfer` | 17.28 s | 83.20 tok/s | 759 | yes |
| 6 | `general_knowledge.dev.mrna-vaccine-mechanism` | 10.96 s | 79.52 tok/s | 512 | yes |
| 7 | `general_knowledge.dev.interest-rates-and-inflation` | 14.78 s | 75.40 tok/s | 640 | yes |
| 8 | `general_knowledge.dev.medical-screening-bayes` | 14.99 s | 79.58 tok/s | 595 | yes |
| 9 | `general_knowledge.dev.antibiotic-resistance` | 13.74 s | 78.97 tok/s | 603 | yes |
| 10 | `general_knowledge.dev.renewable-electricity-matching` | 13.72 s | 78.49 tok/s | 554 | yes |
| 11 | `general_knowledge.dev.distributed-payment-reliability` | 15.06 s | 77.44 tok/s | 616 | yes |
| 12 | `general_knowledge.dev.ml-evaluation-leakage` | 14.56 s | 79.00 tok/s | 667 | yes |
| 13 | `general_knowledge.dev.rag-grounding-evaluation` | 16.57 s | 72.62 tok/s | 591 | yes |

Across all 13 warm screens, mean wall time was 15.03 seconds, median wall time
14.78 seconds and mean decode throughput 80.47 tokens/s. Warm request time
totalled 195.43 seconds. The 13 cold requests totalled 243.50 seconds, with a
mean wall time of 18.73 seconds and mean model-load duration of 2.88 seconds.

Across all thirteen cases with a canonical four-model baseline, Ornith's mean
warm wall time was 15.03 seconds and mean decode throughput was 80.47 tokens/s.
This is screening evidence only: natural response lengths differ, and one
sample per case is not a runtime distribution.

## Comparison status

This is a late-challenger execution and does not alter the explicit canonical
comparison selection. All thirteen cases now have four-model baseline outputs.
Those exact incumbent outputs and Ornith were subsequently rebuilt into
five-candidate bundles and jointly rejudged under the frozen rubrics. The first
eleven were handled in one batch; ML evaluation leakage and RAG grounding were
added in explicit supplemental batches after their incumbent baselines
completed. Ornith achieved the highest five-model mean quality at 87.81, with
three wins, seven second places and three third places. The full protocol, task
results and cognitive-blinding limitation are recorded in
[`ornith-1.5-35b-quality.md`](ornith-1.5-35b-quality.md).

The Hard Knowledge v0.2 execution sequence is now complete. The advance Ornith
outputs never changed the frozen incumbent order or settings; they entered the
joint comparisons only after each missing baseline had completed.
