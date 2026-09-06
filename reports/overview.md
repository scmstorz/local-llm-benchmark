# Aggregate Benchmark Results

Data through: `2026-09-01T07:55:15Z`

This report includes one explicitly selected, judged comparison per case. Final quality scores include invalid generations and rubric caps; the compliant mean excludes outputs that failed deterministic format or completion checks. Performance values are controlled warm-run measurements.

The table is descriptive, not a claim that one model is universally best. The current suite is small and contains heterogeneous tasks.

## Model summary

| Model | Cases | Complete | Compliant | Invalid | Wins | Mean quality | Compliant mean | Mean warm time | Mean output speed |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| muse-glimmer:30b-mlx | 15 | 15 | 15 | 0 | 10 | 85.63 | 85.63 | 37.91 s | 31.65 tok/s |
| ornith-1.5:35b | 2 | 2 | 2 | 0 | 1 | 82.5 | 82.5 | 8.73 s | 84.57 tok/s |
| qwen3.8:27b-mlx | 15 | 15 | 15 | 0 | 2 | 80.93 | 80.93 | 31.98 s | 41.02 tok/s |
| qwen3.6:35b-a3b-mxfp8 | 15 | 15 | 12 | 0 | 2 | 78 | 80.71 | 14.58 s | 82.89 tok/s |
| gpt-oss:20b | 15 | 10 | 10 | 4 | 0 | 53.7 | 74.65 | 27.06 s | 79.36 tok/s |

## Case results

### `summarization.dev.mit-sloan-ai-climate`

Comparison: `comparison-20260828T060458Z-73b47a56` · context: 8192 tokens · performance: controlled

| Rank | Model | Quality | Verdict | Complete | Compliant | Warm time | Output speed | Words |
| ---: | --- | ---: | --- | --- | --- | ---: | ---: | ---: |
| 1 | muse-glimmer:30b-mlx | 90.5 | excellent | yes | yes | 33.84 s | 29.62 tok/s | 516 |
| 2 | qwen3.6:35b-a3b-mxfp8 | 88.5 | good | yes | yes | 11.28 s | 84.08 tok/s | 476 |
| 3 | qwen3.8:27b-mlx | 88.5 | good | yes | yes | 23.95 s | 46.25 tok/s | 592 |
| 4 | gpt-oss:20b | 82 | good | yes | yes | 13.15 s | 91.52 tok/s | 467 |

### `summarization.dev.the-agent-company`

Comparison: `comparison-20260828T170544Z-d6c92325` · context: 16384 tokens · performance: controlled

| Rank | Model | Quality | Verdict | Complete | Compliant | Warm time | Output speed | Words |
| ---: | --- | ---: | --- | --- | --- | ---: | ---: | ---: |
| 1 | muse-glimmer:30b-mlx | 90 | excellent | yes | yes | 82.73 s | 19.51 tok/s | 773 |
| 2 | qwen3.8:27b-mlx | 88 | good | yes | yes | 91.21 s | 21.34 tok/s | 986 |
| 3 | gpt-oss:20b | 86 | good | yes | yes | 39.42 s | 43.99 tok/s | 722 |
| 4 | qwen3.6:35b-a3b-mxfp8 | 72 | usable | yes | yes | 21.85 s | 79.01 tok/s | 868 |

### `summarization.dev.metr-long-software-tasks`

Comparison: `comparison-20260828T180540Z-0a1267f8` · context: 16384 tokens · performance: controlled

| Rank | Model | Quality | Verdict | Complete | Compliant | Warm time | Output speed | Words |
| ---: | --- | ---: | --- | --- | --- | ---: | ---: | ---: |
| 1 | muse-glimmer:30b-mlx | 94.5 | excellent | yes | yes | 65.45 s | 22.88 tok/s | 722 |
| 2 | qwen3.8:27b-mlx | 71 | usable | yes | yes | 46.03 s | 36.1 tok/s | 856 |
| 3 | qwen3.6:35b-a3b-mxfp8 | 69 | usable | yes | yes | 22.13 s | 80.81 tok/s | 891 |
| 4 | gpt-oss:20b | 0 | invalid | no | no | 59.28 s | 44.04 tok/s | 56 |

### `general_knowledge.dev.confidence-intervals`

Comparison: `comparison-20260828T195518Z-856dd260` · context: 8192 tokens · performance: controlled

| Rank | Model | Quality | Verdict | Complete | Compliant | Warm time | Output speed | Words |
| ---: | --- | ---: | --- | --- | --- | ---: | ---: | ---: |
| 1 | muse-glimmer:30b-mlx | 92.5 | excellent | yes | yes | 37.52 s | 23.2 tok/s | 422 |
| 2 | qwen3.8:27b-mlx | 91 | excellent | yes | yes | 26.68 s | 46.71 tok/s | 652 |
| 3 | qwen3.6:35b-a3b-mxfp8 | 90.5 | excellent | yes | yes | 13.35 s | 84.05 tok/s | 579 |
| 4 | gpt-oss:20b | 0 | invalid | no | no | 51.21 s | 50.88 tok/s | 0 |

### `general_knowledge.dev.confidence-intervals-transfer`

Comparison: `comparison-20260829T035945Z-41ceba9a` · context: 8192 tokens · performance: controlled

| Rank | Model | Quality | Verdict | Complete | Compliant | Warm time | Output speed | Words |
| ---: | --- | ---: | --- | --- | --- | ---: | ---: | ---: |
| 1 | muse-glimmer:30b-mlx | 96.5 | excellent | yes | yes | 34.38 s | 36.24 tok/s | 622 |
| 2 | gpt-oss:20b | 75 | good | yes | yes | 16.51 s | 94.15 tok/s | 658 |
| 3 | qwen3.8:27b-mlx | 71.5 | usable | yes | yes | 29.14 s | 48.72 tok/s | 795 |
| 4 | qwen3.6:35b-a3b-mxfp8 | 59 | poor | yes | no | 18.61 s | 85.22 tok/s | 894 |

### `general_knowledge.dev.mrna-vaccine-mechanism`

Comparison: `comparison-20260829T054707Z-7bef0727` · context: 8192 tokens · performance: controlled

| Rank | Model | Quality | Verdict | Complete | Compliant | Warm time | Output speed | Words |
| ---: | --- | ---: | --- | --- | --- | ---: | ---: | ---: |
| 1 | qwen3.8:27b-mlx | 91.5 | excellent | yes | yes | 26.55 s | 42.09 tok/s | 623 |
| 2 | qwen3.6:35b-a3b-mxfp8 | 81.5 | good | yes | yes | 11.34 s | 84.1 tok/s | 543 |
| 3 | gpt-oss:20b | 81 | good | yes | yes | 15.85 s | 91.88 tok/s | 560 |
| 4 | muse-glimmer:30b-mlx | 81 | good | yes | yes | 31.29 s | 34.95 tok/s | 519 |

### `general_knowledge.dev.interest-rates-and-inflation`

Comparison: `comparison-20260829T062601Z-8cb212b9` · context: 8192 tokens · performance: controlled

| Rank | Model | Quality | Verdict | Complete | Compliant | Warm time | Output speed | Words |
| ---: | --- | ---: | --- | --- | --- | ---: | ---: | ---: |
| 1 | qwen3.6:35b-a3b-mxfp8 | 82 | good | yes | yes | 12.61 s | 84.59 tok/s | 631 |
| 2 | muse-glimmer:30b-mlx | 73.5 | usable | yes | yes | 28.88 s | 34.83 tok/s | 498 |
| 3 | qwen3.8:27b-mlx | 63.5 | usable | yes | yes | 22.98 s | 41.74 tok/s | 544 |
| 4 | gpt-oss:20b | 63 | usable | yes | yes | 18.41 s | 89.67 tok/s | 537 |

### `general_knowledge.dev.medical-screening-bayes`

Comparison: `comparison-20260829T075406Z-f1f854c7` · context: 8192 tokens · performance: controlled

| Rank | Model | Quality | Verdict | Complete | Compliant | Warm time | Output speed | Words |
| ---: | --- | ---: | --- | --- | --- | ---: | ---: | ---: |
| 1 | muse-glimmer:30b-mlx | 94.5 | excellent | yes | yes | 25.48 s | 37.24 tok/s | 360 |
| 2 | qwen3.8:27b-mlx | 91.5 | excellent | yes | yes | 25.17 s | 47.29 tok/s | 608 |
| 3 | gpt-oss:20b | 82.5 | good | yes | yes | 27.09 s | 63.94 tok/s | 578 |
| 4 | qwen3.6:35b-a3b-mxfp8 | 80.5 | good | yes | yes | 15.4 s | 84.98 tok/s | 675 |

### `general_knowledge.dev.antibiotic-resistance`

Comparison: `comparison-20260829T084441Z-4dc3483d` · context: 8192 tokens · performance: controlled

| Rank | Model | Quality | Verdict | Complete | Compliant | Warm time | Output speed | Words |
| ---: | --- | ---: | --- | --- | --- | ---: | ---: | ---: |
| 1 | muse-glimmer:30b-mlx | 94 | excellent | yes | yes | 28.64 s | 34.56 tok/s | 431 |
| 2 | qwen3.8:27b-mlx | 86 | good | yes | yes | 20.14 s | 44.86 tok/s | 508 |
| 3 | qwen3.6:35b-a3b-mxfp8 | 81.5 | good | yes | yes | 12.88 s | 83.02 tok/s | 586 |
| 4 | gpt-oss:20b | 57.5 | poor | yes | yes | 15.16 s | 91.41 tok/s | 468 |

### `general_knowledge.dev.renewable-electricity-matching`

Comparison: `comparison-20260829T090820Z-76d94b40` · context: 8192 tokens · performance: controlled

| Rank | Model | Quality | Verdict | Complete | Compliant | Warm time | Output speed | Words |
| ---: | --- | ---: | --- | --- | --- | ---: | ---: | ---: |
| 1 | qwen3.6:35b-a3b-mxfp8 | 84.5 | good | yes | yes | 14.96 s | 76.33 tok/s | 588 |
| 2 | muse-glimmer:30b-mlx | 75.5 | good | yes | yes | 30.6 s | 29.6 tok/s | 430 |
| 3 | qwen3.8:27b-mlx | 67.5 | usable | yes | yes | 45.58 s | 23.7 tok/s | 553 |
| 4 | gpt-oss:20b | 59 | poor | no | no | 29.44 s | 88.51 tok/s | 312 |

### `general_knowledge.dev.distributed-payment-reliability`

Comparison: `comparison-20260829T093603Z-a1fc2009` · context: 8192 tokens · performance: controlled

| Rank | Model | Quality | Verdict | Complete | Compliant | Warm time | Output speed | Words |
| ---: | --- | ---: | --- | --- | --- | ---: | ---: | ---: |
| 1 | qwen3.8:27b-mlx | 77 | good | yes | yes | 33.2 s | 37.95 tok/s | 672 |
| 2 | muse-glimmer:30b-mlx | 70 | usable | yes | yes | 29.56 s | 35.27 tok/s | 483 |
| 3 | qwen3.6:35b-a3b-mxfp8 | 68.5 | usable | yes | yes | 13.44 s | 83.55 tok/s | 614 |
| 4 | gpt-oss:20b | 54 | poor | yes | yes | 15.74 s | 93.67 tok/s | 464 |

### `general_knowledge.dev.ml-evaluation-leakage`

Comparison: `comparison-20260829T105041Z-ff417428` · context: 8192 tokens · performance: controlled

| Rank | Model | Quality | Verdict | Complete | Compliant | Warm time | Output speed | Words |
| ---: | --- | ---: | --- | --- | --- | ---: | ---: | ---: |
| 1 | muse-glimmer:30b-mlx | 93.5 | excellent | yes | yes | 26.17 s | 35.91 tok/s | 493 |
| 2 | qwen3.8:27b-mlx | 89.5 | good | yes | yes | 29.22 s | 43.43 tok/s | 694 |
| 3 | qwen3.6:35b-a3b-mxfp8 | 86 | good | yes | yes | 14.24 s | 84.56 tok/s | 663 |
| 4 | gpt-oss:20b | 80.5 | good | yes | yes | 19.11 s | 91.48 tok/s | 800 |

### `general_knowledge.dev.rag-grounding-evaluation`

Comparison: `comparison-20260829T115954Z-59c6a2df` · context: 8192 tokens · performance: controlled

| Rank | Model | Quality | Verdict | Complete | Compliant | Warm time | Output speed | Words |
| ---: | --- | ---: | --- | --- | --- | ---: | ---: | ---: |
| 1 | muse-glimmer:30b-mlx | 91.5 | excellent | yes | yes | 31.12 s | 31.48 tok/s | 461 |
| 2 | qwen3.8:27b-mlx | 87.5 | good | yes | yes | 26.16 s | 44.75 tok/s | 615 |
| 3 | gpt-oss:20b | 85 | good | yes | yes | 20.28 s | 93.69 tok/s | 625 |
| 4 | qwen3.6:35b-a3b-mxfp8 | 84 | good | yes | yes | 14.88 s | 84.55 tok/s | 646 |

### `source_grounded_writing.dev.ai-transformation-value-gap`

Comparison: `comparison-20260830T172156Z-450bbffe` · context: 8192 tokens · performance: controlled

| Rank | Model | Quality | Verdict | Complete | Compliant | Warm time | Output speed | Words |
| ---: | --- | ---: | --- | --- | --- | ---: | ---: | ---: |
| 1 | muse-glimmer:30b-mlx | 88 | good | yes | yes | 43.2 s | 34.37 tok/s | 448 |
| 2 | ornith-1.5:35b | 82 | good | yes | yes | 8.41 s | 84.42 tok/s | 424 |
| 3 | qwen3.6:35b-a3b-mxfp8 | 79 | good | yes | no | 10.85 s | 82.38 tok/s | 485 |
| 4 | qwen3.8:27b-mlx | 69 | usable | yes | yes | 15.8 s | 42.55 tok/s | 387 |
| 5 | gpt-oss:20b | 0 | invalid | no | no | 36.06 s | 72.39 tok/s | 0 |

### `source_grounded_writing.dev.agentic-software-development-reality-gap`

Comparison: `comparison-20260901T073315Z-42a44ad5` · context: 8192 tokens · performance: controlled

| Rank | Model | Quality | Verdict | Complete | Compliant | Warm time | Output speed | Words |
| ---: | --- | ---: | --- | --- | --- | ---: | ---: | ---: |
| 1 | ornith-1.5:35b | 83 | good | yes | yes | 9.05 s | 84.72 tok/s | 415 |
| 2 | qwen3.8:27b-mlx | 81 | good | yes | yes | 17.82 s | 47.75 tok/s | 466 |
| 3 | qwen3.6:35b-a3b-mxfp8 | 63.5 | usable | yes | no | 10.87 s | 82.08 tok/s | 495 |
| 4 | muse-glimmer:30b-mlx | 59 | poor | yes | yes | 39.85 s | 35.04 tok/s | 418 |
| 5 | gpt-oss:20b | 0 | invalid | no | no | 29.24 s | 89.18 tok/s | 0 |

## Rebuild

```bash
python3 -m local_llm_benchmark report
```

The generated files contain no candidate IDs, run IDs, prompts, source text, or raw model responses.
