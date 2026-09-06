# Agentic Log Incident v0.5 Quality Audit

The frozen 30-cell Capability Sweep completed without a controller failure or
retry. All 30 planned outcomes were retained. Twenty-seven cells produced a
parseable report; three Pi cells reached the 300-second active-time boundary
without one.

The official deterministic result remains **1/30 semantic successes**. This
supplemental audit asks a narrower but indispensable question: are the
free-text claims in each available report grounded in the supplied logs and
appropriately qualified?

## Outcome layers

| Layer | Result |
| --- | ---: |
| Planned cells retained | 30/30 |
| Runtime-complete reports | 27/30 |
| Strict transport compliance | 22/30 |
| Deterministic semantic success | 1/30 |
| Free-text grounding among available reports | 24/27 |
| Free-text review not applicable | 3/30 |
| Deterministic success plus grounded free text | 1/30 |

These layers are not interchangeable. In particular, the prose review does
not repair a missing event in the structured causal chain, a wrongly attached
evidence role or a runtime timeout.

## Complete-system view

`Checks` reports the frozen deterministic checks, including the single schema
check for a timeout without a report. The free-text denominator includes only
parseable reports.

| Harness | Model | Runtime | Strict transport | Semantic | Checks | Grounded prose | Median active time |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: |
| Mini | `qwen3.6:35b-a3b-mxfp8` | 3/3 | 3/3 | 0/3 | 34/45 | 3/3 | 57.59 s |
| Mini | `qwen3.8:27b-mlx` | 3/3 | 3/3 | 0/3 | 39/45 | 3/3 | 81.00 s |
| Mini | `muse-glimmer:30b-mlx` | 3/3 | 3/3 | 0/3 | 39/45 | 3/3 | 62.31 s |
| Mini | `ornith-1.5:35b` | 3/3 | 3/3 | 0/3 | 34/45 | 1/3 | 36.98 s |
| Mini | `gemma4:31b-mlx` | 3/3 | 3/3 | 0/3 | 34/45 | 3/3 | 98.08 s |
| Pi 0.84.4 | `qwen3.6:35b-a3b-mxfp8` | 3/3 | 0/3 | 1/3 | 40/45 | 2/3 | 125.09 s |
| Pi 0.84.4 | `qwen3.8:27b-mlx` | 3/3 | 3/3 | 0/3 | 41/45 | 3/3 | 162.36 s |
| Pi 0.84.4 | `muse-glimmer:30b-mlx` | 1/3 | 1/3 | 0/3 | 13/17 | 1/1 | 300.02 s |
| Pi 0.84.4 | `ornith-1.5:35b` | 2/3 | 0/3 | 0/3 | 27/31 | 2/2 | 289.20 s |
| Pi 0.84.4 | `gemma4:31b-mlx` | 3/3 | 3/3 | 0/3 | 37/45 | 3/3 | 239.20 s |

## The three prose failures

1. Position 7, Ornith with Mini on the clock-skew case, treats the initial
   913-item reconciliation backlog as the count still remaining. The final
   supplied progress event, `REC-702`, records 612 pending after 301 completed.
2. Position 12, Qwen 3.6 with Pi on the clock-skew case, says p95 latency rose
   from 188 ms to more than 2,000 ms. The latter value is one failed request's
   duration in `EDGE-401`, not a p95 statistic.
3. Position 15, Ornith with Mini on the retry case, turns incomplete evidence
   into a categorical claim that no order loss, checkout outage or production
   notification failure occurred. “No evidence of” would be supported; the
   stronger assertion is not.

This distinction is observable in the passing reports: formulations such as
“no evidence supports” and “was not observed” remain bounded, whereas a bare
claim that an outcome did not occur requires stronger evidence.

## Why 1/30 does not mean 29 useless diagnoses

Every one of the 27 parseable reports passed the deterministic root-cause,
trigger, affected-scope and citation-integrity checks. The failures cluster in
exact representation and evidence completeness:

| Failed check | Cells |
| --- | ---: |
| Causal chain | 18 |
| Critical evidence role-linking | 15 |
| Rejected-hypothesis evidence | 13 |
| Bounded impact | 6 |
| Required uncertainties | 5 |
| Recovery status | 4 |
| Report schema after timeout | 3 |

The official score is a conjunction over a demanding verified-outcome
contract. It correctly says that only one report satisfied every required
structured condition. It does not say that only one model run understood the
incident.

## Practical reading

- Qwen 3.8 is the most consistent measured deployment here: 6/6 runtime and
  transport completion, 80/90 structured checks and 6/6 grounded reports. It
  still missed at least one exact requirement in every cell.
- Qwen 3.6 produced the only full deterministic success, under Pi, and has the
  lower cross-system median time of the two Qwen deployments. Pi normalized
  all three of its responses, however, and one report conflated request
  duration with p95.
- Glimmer is strong and fast under Mini, but two of its three Pi cells reached
  the 300-second boundary. This is a complete-system interaction, not evidence
  that the model alone is unreliable.
- Ornith is the fastest Mini deployment, but two of its three Mini reports
  contain unsupported prose and its Pi condition includes one timeout and two
  normalized responses.
- Gemma is runtime- and transport-stable in all six cells, but slower and did
  not gain an exact semantic success in this sweep.

There is no defensible universal winner from one attempt per exact
configuration. For this task family, the evidence favors Qwen 3.8 for stable,
high structured coverage and Qwen 3.6/Pi as the only demonstrated exact
success. A later repetition study is required before either becomes a
reliability claim.

## Judge limitation

The review was performed in the interactive Codex session without a paid judge
API. The judge had already seen the model/run mapping, so this is not blinded
assessment evidence. The fixed claim-level rule, exact position list and
source-report hash are preserved in the companion JSON for reproducibility.
