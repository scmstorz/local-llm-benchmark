# Repeated Quality Evaluation

Study: `quality-study-20260909T152526Z-090c25b9`

This report was generated only after scalar and pairwise judgments were
schema-validated, frozen, and content-hashed. Model identity and runtime
metadata were revealed afterwards.

Scores use task-specific 0–100 rubrics. Quality, reliability, performance
and variation remain separate; no composite score is reported. With this
small sample, timings are descriptive and no tail percentiles or precise
failure probabilities are claimed.

## Results

| Case | Model | Scores | Mean | Median | Range | Pair W-L-T | Unique outputs | Technical |
| --- | --- | --- | ---: | ---: | --- | --- | ---: | --- |
| `general_knowledge.dev.medical-screening-bayes` | `muse-glimmer:30b-mlx` | 80, 92.5, 94.5, 81.5, 92 | 88.10 | 92.00 | 80–94.5 | 2-3-0 | 5 | 5/5 |
| `general_knowledge.dev.medical-screening-bayes` | `qwen3.8:27b-mlx` | 92.5, 90, 92.5, 92.5, 92.5 | 92.00 | 92.50 | 90–92.5 | 3-2-0 | 2 | 5/5 |
| `general_knowledge.dev.ml-evaluation-leakage` | `muse-glimmer:30b-mlx` | 85.5, 94.5, 95.5, 91.5, 94 | 92.20 | 94.00 | 85.5–95.5 | 3-2-0 | 5 | 5/5 |
| `general_knowledge.dev.ml-evaluation-leakage` | `qwen3.8:27b-mlx` | 92.5, 93, 91.5, 92.5, 91.5 | 92.20 | 92.50 | 91.5–93 | 2-3-0 | 3 | 5/5 |

## Recurring errors

- `general_knowledge.dev.medical-screening-bayes` / `muse-glimmer:30b-mlx`: certainty_inflation × 2, contradiction × 2
- `general_knowledge.dev.medical-screening-bayes` / `qwen3.8:27b-mlx`: other × 5
- `general_knowledge.dev.ml-evaluation-leakage` / `muse-glimmer:30b-mlx`: certainty_inflation × 3
- `general_knowledge.dev.ml-evaluation-leakage` / `qwen3.8:27b-mlx`: certainty_inflation × 5

## Freeze provenance

- Scalar judgments: `6349b889f68bed77e75dee1350341636bd28606b5c50874701ebf1567e905885`
- Pairwise judgments: `6ab5b6a5f9e511860d63788b389bb48d17220e204594c653a2e8fcb26e500816`
