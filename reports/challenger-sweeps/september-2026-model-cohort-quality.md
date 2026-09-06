# September 2026 Model Cohort — Joint Quality Report

Date: 2026-09-03

Evaluation batch: `challenger-evaluation-20260903T074940Z-ae83d012`

Independent score freeze: `4f2b52a5ad7155d73fe6a2ece17bec012e6b1266f50a1f17172556053015e04a`

Final blind freeze: `3614a407e4c37a81b1eb3526e96608e612bb85e57a3af244104ab90d06a534f0`

Status: 107 candidates across 15 cases jointly judged

The sanitized machine-readable result is
[`september-2026-model-cohort-quality.json`](september-2026-model-cohort-quality.json).

## Outcome

`gemma4:31b-mlx` is the clear admission from this three-model cohort. It scored
89.13/100 across all 15 cases, passed every hard output constraint and did not
produce a poor or invalid answer. It also narrowly leads the seven deployments
with full-suite evidence in this single joint judgment batch.

Nemotron is an unusually sharp speed-quality trade-off rather than a general
winner. Its median warm wall time was 11.92 seconds and median decode throughput
100.89 tokens/s, but its mean quality was 70.0, five outputs violated hard
constraints and seven final scores fell below 60. Granite averaged 69.23 with
six hard output failures and eight poor scores. Granite's run was also both
slow and affected by standby and inconsistent Ollama duration telemetry.

## Full-suite context

| Rank | Deployment | n | Mean | Median | Excellent | Poor / invalid |
| ---: | --- | ---: | ---: | ---: | ---: | ---: |
| 1 | `gemma4:31b-mlx` | 15 | **89.13** | 90 | 8 | **0** |
| 2 | `muse-glimmer:30b-mlx` | 15 | 89.00 | **93** | **9** | 1 |
| 3 | `qwen3.8:27b-mlx` | 15 | 88.13 | 91 | **9** | **0** |
| 4 | `qwen3.6:35b-a3b-mxfp8` | 15 | 84.47 | 87 | 4 | 1 |
| 5 | `nemotron-3.5-lightning:30b-mlx` | 15 | 70.00 | 74 | 1 | 7 |
| 6 | `granite4.2:30b` | 15 | 69.23 | 59 | 1 | 8 |
| 7 | `gpt-oss:20b` | 15 | 59.27 | 77 | 3 | 5 |

Ornith scored 90.5 across the two writing cases present in this batch, but it
has no candidate in the other thirteen cases and is therefore not ranked with
the full-suite deployments.

Every case uses a normalized 0–100 rubric, but the mean is only a descriptive
summary of this personal task mix. The 0.13-point Gemma/Glimmer difference is
not a statistically meaningful claim of universal superiority. The more robust
observations are Gemma's absence of hard failures, Glimmer's higher median and
nine excellent cases, and Qwen 3.8's similarly failure-free consistency.

## New cohort by task family

| Deployment | Summarization | General knowledge | Source-grounded writing | Overall |
| --- | ---: | ---: | ---: | ---: |
| `gemma4:31b-mlx` | **90.00** | **90.80** | **79.50** | **89.13** |
| `nemotron-3.5-lightning:30b-mlx` | 77.00 | 70.00 | 59.50 | 70.00 |
| `granite4.2:30b` | 78.83 | 67.50 | 63.50 | 69.23 |

Gemma is excellent on the three summaries and ten difficult knowledge tasks,
but its two writing posts score only 84 and 75. It should therefore join the
Capability Sweep as a strong general-purpose candidate, not displace Ornith or
Glimmer as a writing specialist on two observations.

## New cohort by case

| Case | Gemma | Nemotron | Granite |
| --- | ---: | ---: | ---: |
| MIT Sloan AI and climate | 93 | 88 | 87.5 |
| TheAgentCompany | 91 | 84 | 90 |
| METR long software tasks | 86 | 59 | 59 |
| Confidence intervals | 96 | 59 | 59 |
| Confidence-interval transfer | 94 | 59 | 59 |
| mRNA vaccine mechanism | 94 | 82 | 59 |
| Interest rates and inflation | 90 | 59 | 82 |
| Medical screening and Bayes | 96 | 92 | 88 |
| Antibiotic resistance | 85 | 76 | 87 |
| Renewable electricity matching | 85 | 84 | 54 |
| Distributed payment reliability | 89 | 78 | 52 |
| ML evaluation leakage | 88 | 55 | 52 |
| RAG grounding evaluation | 91 | 56 | 83 |
| AI transformation value gap | 84 | 74 | 75 |
| Agentic software development reality gap | 75 | 45 | 52 |

## What separated the deployments

Gemma's strength is reliability across heterogeneous instructions. It avoided
all length, language, source-label and truncation failures. Its best results
were the confidence-interval, medical-screening and mRNA cases. Its weaker
writing result omitted too much of the source packet and compressed important
study limitations, but remained usable and compliant.

Nemotron's low latency came with poor instruction control and several semantic
failures. It exceeded four word limits, exposed source labels in one post,
misstated the frequentist interpretation of a confidence interval, defined the
METR task horizon incorrectly and reversed the central randomized developer
study result from a 19-percent slowdown to a productivity increase.

Granite was strongest on TheAgentCompany, medical screening and antibiotic
resistance. Its median score of 59 reflects repeated hard caps: six formal
constraint failures plus a critical missing negation in the mRNA answer. It
also left provider-side payment idempotency unsafe and confused several
electricity-system concepts.

## Protocol and limits

Candidate IDs were independently randomized for every case. The private map
remained unopened through all 107 scalar judgments and 83 required pairwise
checks. Every pair within three points was directly compared; the independent
order was retained and exact ties remained ties. No score changed.

This was not pristine cognitive blinding. The interactive judge had previously
seen some baseline outputs and execution characteristics, so stylistic or
deterministic clues could make identities inferable. The joint batch controls
judge drift better than comparing new scores with old scores, but it remains a
single interactive judgment pass rather than a stochastic judge study.

The historical canonical reports are not overwritten. This late-challenger
batch is a separate internally comparable evidence layer. Performance values
are also single warm screens, not distributions; Granite's values are
diagnostic only because of the standby and telemetry anomalies documented in
the execution record.

## Practical decision

Admit `gemma4:31b-mlx` as a strong Track A generalist and prioritize it for
future controlled comparisons. Keep `nemotron-3.5-lightning:30b-mlx` as an
interesting high-throughput specialist candidate whose use requires strict
verifiers and format enforcement. Do not use `granite4.2:30b` as a default in
the tested local configuration; retain its raw results as valuable negative
evidence.

None of these Track A results qualifies a model for Mini, Pi or OpenCode.
Track B admission still requires a separate executable harness qualification.
