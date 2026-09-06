# Ornith 1.5 35B Challenger — Joint Quality Report

Date: 2026-08-29  
Execution sweep: `sweep-20260829T100955Z-f96e5d8b`  
Evaluation batch: `challenger-evaluation-20260829T102544Z-0388dba0`  
Blind judgment freeze: `c9208361029c84298a2d73bfdf8dec0515585223a0ef597f290625e59ac0fa3a`  
Supplemental ML batch: `challenger-evaluation-20260829T105731Z-6e4fc2bc`
Supplemental freeze: `bc9ff6a1625b64dd0ae455c6f16a8e0f1d658430f584e9d245606be52a4db45c`
Supplemental RAG batch: `challenger-evaluation-20260829T120744Z-774fb473`
Supplemental RAG freeze: `bcbdcc3ec69625c7399fee97eaaf951b560ec814f6ebb193569f9b14690c9193`
Status: thirteen-case late-challenger quality comparison complete

The sanitized machine-readable result is
[`ornith-1.5-35b-quality.json`](ornith-1.5-35b-quality.json).

## Scope and protocol

Ornith was added after the four incumbent deployments had completed their
canonical comparisons. Comparing a fresh Ornith-only score with the historical
scores would have confounded deployment quality with interactive-judge drift.
The initial evaluation rebuilt eleven five-candidate bundles from the exact
historical warm responses and Ornith's warm response, then rejudged all 55
outputs in one source-grounded batch under the already frozen case rubrics.
After the pre-registered incumbent run for ML evaluation leakage completed, a
supplemental five-candidate bundle reused its four exact warm responses and the
already preserved Ornith output. All five were judged together under the same
freeze-before-unblinding rule.

The final RAG-grounding case followed the same late-baseline path. Its five
independent judgments were additionally frozen before the three required
pairwise checks, after which the complete blind record was frozen separately.

Candidate IDs were randomized separately for every case. In the initial batch,
the private mapping remained unopened until all 55 scalar judgments and 20
required pairwise checks had been written and frozen. The two supplemental
batches added ten scalar judgments and five pairwise checks under their own
pre-unblinding freezes. Pairwise checks were triggered whenever two scores
differed by no more than three points. Every check retained the independent
ordering and no score was adjusted.

This was not a pristine cognitively blind trial. The judge had already seen
Ornith's per-case word counts in the execution report, so response length could
make the challenger inferable in some bundles. Randomized IDs and the unopened
map prevented direct identity disclosure, but the result must be described as
a joint late-challenger rejudgment with limited cognitive blinding.

All thirteen current development cases now have both canonical four-model
evidence and one internally comparable five-way late-challenger judgment.

## Aggregate result

| Rank | Deployment | Mean quality | Median quality | Wins | Top two | Invalid / poor | Mean warm wall | Mean decode |
| ---: | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 1 | `ornith-1.5:35b` | **87.81** | 91.00 | 3 | **10** | 0 / 0 | **15.03 s** | 80.47 tok/s |
| 2 | `muse-glimmer:30b-mlx` | 87.12 | 90.50 | **5** | **10** | 0 / 0 | 37.36 s | 31.18 tok/s |
| 3 | `qwen3.8:27b-mlx` | 82.00 | 83.50 | 2 | 3 | 0 / 0 | 34.31 s | 40.38 tok/s |
| 4 | `qwen3.6:35b-a3b-mxfp8` | 79.92 | 82.50 | 3 | 3 | 0 / 1 | 15.15 s | **82.99 tok/s** |
| 5 | `gpt-oss:20b` | 61.50 | 74.50 | 0 | 0 | 2 / 3 | 26.20 s | 79.14 tok/s |

Quality points use each case's normalized 0–100 rubric. The mean is useful as
a compact cross-case summary, but it is not a universal intelligence score and
does not replace the task-level results.

Ornith has the highest observed mean quality and never finishes below third. It
does not win the most cases: Glimmer wins five and Qwen 3.6 wins three. Ornith's
aggregate lead comes from consistency—three wins, seven second places, three
third places, no invalid result and no score below 72.5.

The warm values are screening measurements, not latency distributions.
Incumbent timings come from their canonical controlled comparison sessions,
while Ornith ran later in its own controlled suite sweep. Natural answer lengths
also differ. Ornith has the shortest observed thirteen-case mean wall time by
0.12 seconds over Qwen 3.6, while Qwen 3.6 has 2.52 more output tokens per
second. This supports a strong provisional speed-quality result, not a precise
runtime superiority claim.

## Ornith by case

| Case | Quality | Rank | Warm wall | Decode | Main judgment |
| --- | ---: | ---: | ---: | ---: | --- |
| MIT Sloan AI and climate | 91.5 | 2 / 5 | 11.46 s | 86.59 tok/s | Comprehensive and conditional; minor attribution and German-language awkwardness |
| TheAgentCompany | 91.5 | 2 / 5 | 17.46 s | 82.89 tok/s | Highly precise; misses contributor effort and underdescribes the LLM evaluator |
| METR long software tasks | 91.5 | 2 / 5 | 22.14 s | 83.80 tok/s | Strong scaffold-aware account; misses some run detail and extends one date bound |
| Confidence intervals | 88.5 | 3 / 5 | 12.70 s | 88.55 tok/s | Correct overall; awkward numerical wording and an indirect precision-versus-bias treatment |
| Confidence-interval transfer | 88.5 | 2 / 5 | 17.28 s | 83.20 tok/s | Thorough, but contains one contradictory bias direction and mild causal overstatement |
| mRNA vaccine mechanism | 88.5 | 2 / 5 | 10.96 s | 79.52 tok/s | Clear and calibrated; immune memory is implied rather than developed |
| Interest rates and inflation | 72.5 | 3 / 5 | 14.78 s | 75.40 tok/s | Broad coverage, but automatic exchange-rate language, imprecision and visible language corruption |
| Medical screening and Bayes | 91.0 | 2 / 5 | 14.99 s | 79.58 tok/s | Complete and accessible; confirmation is not made explicit |
| Antibiotic resistance | **94.5** | **1 / 5** | 13.74 s | 78.97 tok/s | Best evolutionary, stewardship and One Health integration |
| Renewable electricity matching | 76.0 | 3 / 5 | 13.72 s | 78.49 tok/s | Broadly complete, but overstates annual procurement effects and misses storage dimensions |
| Distributed payment reliability | **83.0** | **1 / 5** | 15.06 s | 77.44 tok/s | Best end-to-end failure-boundary design, despite one contradictory timeout timeline |
| ML evaluation leakage | **91.5** | **2 / 5** | 14.56 s | 79.00 tok/s | Complete leakage and nested-CV account; final configuration and test-inspection wording remain slightly ambiguous |
| RAG grounding evaluation | **93.0** | **1 / 5** | 16.57 s | Best stage separation and claim-level evidence contract; rank-position factorial design remains partial |

## Interpretation

Ornith is the strongest observed default candidate in the present capability
sweep. It combines Glimmer-like aggregate quality with Qwen-3.6-like latency
and produced a valid, usable answer in every jointly judged case. Its three
paper summaries are especially consistent: all score 91.5 and rank second.

The three wins are also informative. Antibiotic resistance rewards broad,
source-grounded synthesis across evolution, patient care and One Health.
Distributed payment reliability rewards integrated reasoning across ambiguous
timeouts, external idempotency, local state, outbox boundaries and
reconciliation. RAG grounding rewards stage-specific diagnosis, claim-level
support and adversarial evaluation design. Ornith handled all three forms of
integration better than the exact incumbent candidates in this rejudgment.

The weaker cases prevent a blanket conclusion. The interest-rate answer used
overconfident exchange-rate language and contained corrupted wording. The
renewable-electricity answer blurred accounting value, additional generation
and actual emissions effects. These are substantive calibration failures, not
mere style preferences.

This batch's rejudged incumbent scores intentionally do not replace the
canonical score files. Interactive judge calibration can change over time; the
new five-way scores form one internally comparable late-challenger batch,
whereas the canonical index remains the record of each original experiment.
Future publication should present both batch protocols and the
cognitive-blinding limitation beside the aggregate. Both supplemental hard-case
batches required an explicit late-baseline assembly flag because their
incumbent comparisons completed after Ornith's already frozen suite sweep;
these exceptions are recorded rather than silently rewriting sweep history.

## Practical decision

For the current single-turn German summarization and difficult
general-knowledge workload, `ornith-1.5:35b` becomes the provisional default
deployment to test first. Qwen 3.6 remains the throughput reference and a useful
fast alternative. Glimmer remains a high-quality specialist with the most case
wins, but its observed mean warm wait is much longer.

The frozen Hard Knowledge v0.2 Capability Sweep is complete. The next study
should be chosen explicitly rather than adding more similar cases by inertia:
either a small Quality Stochasticity Study on discriminative cases, a controlled
Performance and Reliability Study, or the first source-grounded synthesis case.
