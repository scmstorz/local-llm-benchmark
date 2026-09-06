# Agentic Log Incident Capability Sweep v0.2 — Post-hoc Analysis

This document adds diagnostics to the frozen primary report. It does not
change any run, verifier criterion or primary outcome.

## Primary result

- Verified success: 0/30
- Runtime-complete: 30/30
- Schema-valid reports: 22/30
- Result: no tested complete system met the frozen deployment threshold.

## System diagnostics

The check column is diagnostic coverage, not a normalized quality score.
Timing is median [minimum, maximum] over three heterogeneous cases and is
descriptive only because Spotlight load was present at launch.

| Harness | Model | Verified | Schema-valid | Verifier checks | Active time |
| --- | --- | ---: | ---: | ---: | ---: |
| Mini | `qwen3.6:35b-a3b-mxfp8` | 0/3 | 3/3 | 24/42 | 54.11 s [51.78, 123.64] |
| Mini | `qwen3.8:27b-mlx` | 0/3 | 3/3 | 36/42 | 85.52 s [83.90, 100.57] |
| Mini | `muse-glimmer:30b-mlx` | 0/3 | 3/3 | 31/42 | 68.19 s [56.94, 71.37] |
| Mini | `ornith-1.5:35b` | 0/3 | 3/3 | 26/42 | 40.14 s [32.88, 50.97] |
| Mini | `gemma4:31b-mlx` | 0/3 | 3/3 | 20/42 | 60.54 s [50.99, 68.99] |
| Pi 0.84.4 | `qwen3.6:35b-a3b-mxfp8` | 0/3 | 0/3 | n/a | 109.06 s [93.96, 138.34] |
| Pi 0.84.4 | `qwen3.8:27b-mlx` | 0/3 | 1/3 | 13/14 | 134.73 s [121.11, 261.67] |
| Pi 0.84.4 | `muse-glimmer:30b-mlx` | 0/3 | 3/3 | 30/42 | 254.30 s [238.81, 274.28] |
| Pi 0.84.4 | `ornith-1.5:35b` | 0/3 | 0/3 | n/a | 256.40 s [143.86, 297.13] |
| Pi 0.84.4 | `gemma4:31b-mlx` | 0/3 | 3/3 | 21/42 | 269.96 s [199.98, 294.09] |

## Closest strict outcomes

| Harness | Model | Case | Checks | Missing criteria |
| --- | --- | --- | ---: | --- |
| Mini | `qwen3.8:27b-mlx` | Checkout pool regression | 13/14 | distractor_rejection |
| Pi 0.84.4 | `qwen3.8:27b-mlx` | Checkout pool regression | 13/14 | incident_window_utc |
| Mini | `qwen3.8:27b-mlx` | Clock skew partial recovery | 12/14 | incident_window_utc, critical_evidence |

## Recurring misses in schema-valid reports

| Essential check | Failed reports |
| --- | ---: |
| `incident_window_utc` | 20/22 |
| `causal_chain` | 17/22 |
| `critical_evidence` | 16/22 |
| `distractor_rejection` | 16/22 |
| `affected_scope` | 11/22 |
| `bounded_impact` | 10/22 |
| `remediation` | 9/22 |
| `uncertainty` | 4/22 |
| `recovery_status` | 3/22 |
| `root_cause` | 1/22 |

## Post-hoc response-envelope sensitivity

This exploratory check removes only surrounding prose or Markdown fences
and then runs the same frozen verifier. It is not a primary rescore.

- Strictly invalid report responses: 8
- Embedded JSON objects recovered: 8
- Schema-valid after recovery: 7
- Fully verified after recovery: 0
- Primary outcomes changed: no

| Model | Case | Envelope | Recovered checks |
| --- | --- | --- | ---: |
| `qwen3.8:27b-mlx` | Retry queue amplification | `surrounding_text` | 0/1 |
| `ornith-1.5:35b` | Checkout pool regression | `surrounding_text` | 12/14 |
| `qwen3.8:27b-mlx` | Clock skew partial recovery | `surrounding_text` | 9/14 |
| `qwen3.6:35b-a3b-mxfp8` | Clock skew partial recovery | `markdown_code_fence` | 7/14 |
| `ornith-1.5:35b` | Retry queue amplification | `markdown_code_fence` | 8/14 |
| `ornith-1.5:35b` | Clock skew partial recovery | `markdown_code_fence` | 11/14 |
| `qwen3.6:35b-a3b-mxfp8` | Retry queue amplification | `markdown_code_fence` | 8/14 |
| `qwen3.6:35b-a3b-mxfp8` | Checkout pool regression | `markdown_code_fence` | 12/14 |

## Manual calibration and specification audit

A post-hoc review of the three closest strict outcomes found that the
Qwen 3.8 responses were useful analyst drafts. One miss was a narrow
evidence-to-hypothesis assignment; two included materially different
incident-start choices, and one also misassigned a recovery evidence role.
The strict primary failures remain unchanged.

Calibration conclusion: The nearest Qwen 3.8 outputs were useful analyst drafts, but none was a machine-verifiable autonomous outcome under the frozen contract.

The audit also found a blocking specification mismatch: the visible task
defines `last_observed_utc` but never defines `start_utc`, while the hidden
verifier requires the first observed user-facing impact. Deployment, trigger
or component-admission timestamps are plausible alternatives under the
visible wording. This check failed in 20/22 schema-valid reports.

Therefore v0.2 is retained as historical protocol evidence but is not
decision-ready evidence of model incapability. A v0.3 task contract must
define the incident start before any confirmation or replication run.

## Case diagnostics

| Case | Verified | Schema-valid | Verifier checks |
| --- | ---: | ---: | ---: |
| Checkout pool regression | 0/10 | 8/10 | 84/112 |
| Retry queue amplification | 0/10 | 7/10 | 57/98 |
| Clock skew partial recovery | 0/10 | 7/10 | 60/98 |

## Interpretation

- Qwen 3.8 produced all three strict Mini reports and covered 36/42 checks. All three observed outcomes within two checks of strict success used Qwen 3.8, including the one close Pi outcome.
- Mini produced 15/15 schema-valid reports; Pi produced 7/15. This is an observed complete-system difference, not an isolated causal harness effect.
- Pi's eight strict format failures all contained an embedded JSON object, but envelope stripping still yielded zero fully verified reports. Format compliance matters, yet does not explain the zero-success result by itself.
- Exact incident timing, causal-chain reconstruction, distractor rejection and critical-evidence selection are the dominant strict-verifier gaps.
- No productive default route can be certified from v0.2. The specification mismatch must be corrected before deciding whether the models or the task contract caused the zero-success result.

## Interpretation boundaries

- Zero verified successes means no tested system met the frozen deployment threshold in its single observed attempt.
- Partial check counts locate failure modes but are not a substitute primary score and are not normalized quality points.
- Each system-model-case cell has n=1, so no reliability or stochasticity claim is supported.
- Mini and Pi differ as complete systems; this design cannot isolate a causal harness effect.
- The response-envelope sensitivity was chosen after observing failures and is exploratory only.
- The visible start-time definition and hidden verifier expectation were not fully aligned, so v0.2 is not decision-ready capability evidence.
- No verifier criterion is removed or weakened after observing model output.
- No composite ranking or tail-latency claim is produced.
