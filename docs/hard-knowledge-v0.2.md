# Hard Knowledge v0.2

This document freezes the second general-knowledge block before execution. The
machine-readable contract is
[`tasks/general-knowledge/hard-knowledge-v0.2.json`](../tasks/general-knowledge/hard-knowledge-v0.2.json).

## Research question

Do the model reversals observed in the first four general-knowledge cases
persist across a broader, harder and predeclared set, or does one deployment
develop a stable quality or quality-latency advantage?

This block is not a trivia collection. Each prompt presents a plausible but
flawed inference and asks the candidate to recover the mechanism, boundaries,
trade-offs and appropriate evidence or system design.

## Frozen cases

| Order | Case | Main capability under test |
| ---: | --- | --- |
| 1 | Medical screening and Bayes | Natural frequencies, base rates and biased screening outcomes |
| 2 | Antibiotic resistance | Evolution, transmission and stewardship trade-offs |
| 3 | Renewable electricity matching | Annual accounting, hourly balancing and flexibility timescales |
| 4 | Distributed payment reliability | Failure boundaries, idempotency and reconciliation |
| 5 | ML evaluation leakage | Preprocessing leakage, selection bias and nested CV |
| 6 | RAG grounding evaluation | Pipeline diagnosis, claim support and citation metrics |

Each case contains a German candidate prompt, an English project-authored
reference dossier compiled from authoritative sources, source metadata and a
case-specific benchmark card. The candidate cannot see the dossier and cannot
browse or use tools. The interactive judge receives the dossier after the
candidate artifacts have been anonymized.

## Execution progress

All six frozen cases have completed their canonical four-model comparison and
judgment. The two cases whose Ornith outputs existed before their incumbent
baselines—ML evaluation leakage and RAG grounding—were assembled only through
the explicitly recorded late-baseline path after the scheduled comparisons
finished. No result changed this manifest's frozen case order, model order or
inference settings. Hard Knowledge v0.2 is now an execution-complete Capability
Sweep block; distributional quality and reliability claims remain deferred to
their separately designed studies.

## Balanced execution order

The aliases are A = Qwen 3.6, B = Qwen 3.8, C = GPT-OSS and D = Muse Glimmer.
The within-case orders are frozen as `ABDC`, `BCAD`, `CDBA`, `DACB`, `ADCB`
and `CBAD`. Across six cases, every model occurs once or twice in every
position. This controls gross order effects without multiplying the already
substantial runtime.

The first comparison is therefore invoked as:

```bash
python3 -m local_llm_benchmark compare \
  --case tasks/general-knowledge/dev/medical-screening-bayes/case.json \
  --models \
    qwen3.6:35b-a3b-mxfp8 \
    qwen3.8:27b-mlx \
    muse-glimmer:30b-mlx \
    gpt-oss:20b \
  --temperature 0 \
  --seed 42 \
  --num-ctx 8192 \
  --num-predict 2600 \
  --think false \
  --keep-alive 10m \
  --timeout 600
```

The exact order for later cases must come from the manifest, not from this
example or memory.

## Measurement and judgment

The existing economical protocol remains in force: one explicit cold run and
one immediate warm run per model. Two extra warm repetitions are added only if
timing is close or unstable enough to affect a decision. Five repetitions are
reserved for finalists or publication-grade confirmation.

Before each comparison, verify that the Mnemosyn and News-App workers are
stopped, unload Ollama models and observe an empty Ollama state for 30 seconds.
After the comparison, unload the final model and repeat the observation.

Quality is judged case by case before unblinding. All six frozen cases remain
in the primary aggregate, including invalid or capped outputs. Case-level
results remain primary; the six-case mean, median, compliance rate, model wins,
warm latency and Pareto frontiers are descriptive summaries. No model run was
performed while preparing or freezing this block.
