# Performance and Reliability Study v0.1 — Interpretation

This document interprets the immutable generated
[aggregate](performance-reliability-v0.1.md). It does not replace or filter the
primary results. The study contains 80 measured requests and 16 excluded
warm-ups across two Ollama deployments and two deliberately separate workload
types.

## Result at a glance

| Workload | Deployment | Technical completion | Output-contract pass | Wall P50 | Wall P90 | Maximum | Decode tok/s P50 |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: |
| Controlled 256-token decode | `ornith-1.5:35b` | 20/20 | 20/20 | 2.83 s | 3.16 s | 9.54 s | 92.21 |
| Controlled 256-token decode | `qwen3.8:27b-mlx` | 20/20 | 20/20 | 3.63 s | 4.82 s | 18.58 s | 71.75 |
| Natural German answer | `ornith-1.5:35b` | 20/20 | 20/20 | 11.95 s | 12.59 s | 39.78 s | 92.82 |
| Natural German answer | `qwen3.8:27b-mlx` | 20/20 | 20/20 | 29.25 s | 128.81 s | 148.33 s | 43.02 |

P90 uses nearest rank and is exploratory at `n = 20`. P95 and P99 are not
reported. Technical completion and the deterministic output contract were
perfect in this observed sample; semantic quality was intentionally not
evaluated.

## What the controlled workload establishes

Both deployments received the same prompt bytes and generated exactly 256
evaluated output tokens in every valid observation. On this workload, Ornith's
median wall time was 22% lower and its median decode throughput was 29% higher
than Qwen's. Ornith also exposed first content sooner: a 0.055-second median
versus 0.135 seconds for Qwen.

This is the cleanest runtime comparison in the study. It supports the bounded
claim that this exact Ornith deployment decoded the fixed workload faster than
this exact Qwen deployment on the measured Mac/Ollama configuration. It is not
a model-family or hardware-independent claim.

Both controlled distributions contain a localized slowdown. Ornith reached
8.60 and 9.54 seconds in two observations; Qwen reached 11.26 and 18.58
seconds. Related slowdowns also appeared in the natural workload during the
same third-segment period. The controller found no declared blocking process,
runtime drift, digest drift or unexpected loaded model, but the pattern shows
that its resource gate did not capture every relevant machine-state effect.

## What the natural workload adds

The natural German answers were not length-controlled. Ornith's median output
was 1,105 evaluated tokens and Qwen's was 1,247, so wall-time differences
combine answer length with runtime behavior. Even with that qualification,
the user-facing difference was large: Ornith's median was 11.95 seconds and
Qwen's was 29.25 seconds. Ornith's median decode throughput was more than twice
Qwen's in this condition.

The study does not judge whether either set of natural answers was semantically
correct. Prior capability evidence motivated the deployments, but it cannot be
silently imported as the quality result for these 40 new answers. The natural
workload therefore informs latency and observed contract reliability only.

## Notebook-standby sensitivity

Four Qwen natural-output observations, repetitions 11–14, crossed a macOS
notebook-standby interval. Their active monotonic/Ollama durations were
123.94–148.33 seconds, while their UTC start-to-end intervals contained an
additional 1,183–2,144 seconds. All other completed measurements differed by
at most 0.19 seconds between those clocks.

The four observations remain in the immutable primary distribution because
standby exclusion was not predeclared. They are also not ordinary experienced
wall-clock latency: the clocks used by Python and Ollama did not count the
suspended interval. They may additionally reflect uncontrolled machine-state
drift around standby.

For sensitivity only, removing those four flagged observations leaves 16 Qwen
natural-output measurements:

| View | n | Wall P50 | Minimum | Maximum | Tail statistic |
| --- | ---: | ---: | ---: | ---: | --- |
| Primary, all predeclared observations | 20 | 29.25 s | 26.47 s | 148.33 s | P90 128.81 s |
| Standby-flagged observations omitted | 16 | 28.82 s | 26.47 s | 73.00 s | none permitted at `n < 20` |

The median conclusion is stable, but the Qwen natural P90 is not robust to the
standby event. It must not be presented as an intrinsic model tail estimate.

## Decision relevance

- Both deployments completed every planned request and passed every output
  contract in this sample. This is positive observed evidence, not proof of a
  zero population failure rate.
- Ornith is the clear speed choice for these direct text-generation workloads.
  The controlled workload shows that the advantage is not explained only by
  shorter natural answers.
- Qwen's prior role as the safer difficult-knowledge default remains a quality
  decision. This performance study does not overturn it; it quantifies the
  latency paid for that choice under these conditions.
- The tail observations justify distribution reporting. They also show why a
  future protocol should detect host suspension and richer machine-state drift
  explicitly rather than relying only on process and Ollama-state guards.

No composite score is produced. The operational choice remains a trade-off
between independently reported quality evidence, latency, and reliability.
