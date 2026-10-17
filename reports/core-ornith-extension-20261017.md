# Ornith extension: four deployed systems compared

Ornith 1.5 adds ten newly executed cells to the same six-task profile on 2026-10-17. The thirty Qwen 3.8, Gemma 4 and Nemotron 3.5 Lightning cells are exact preserved measurements from the earlier round. This view therefore covers forty cells, with ten new executions and thirty declared references. Nemotron already has all ten measured cells; it was not rerun for this extension.

Ollama remains 0.40.5; the reference artifacts, hardware and all 409 previously bound source files still match. Ornith ran later that day as GGUF/Q4_K_M, while the references use MLX. These are deployed-system comparisons, including runtime backend and harness, rather than isolated model-family effects. Each cell is one observation; no reliability probability or combined model rank is inferred.

Exact digests, provenance, configurations, outcome layers and native timing counters: [comparison JSON](core-ornith-extension-20261017.json). Selection: [four-model cohort](../models/cohorts/core-ornith-extension-2026-10-17.json). The [previous comparison](core-first-comparison-20261017.md) and its judgment batch remain unchanged.

## Joint text evaluation

A new evaluation batch jointly assesses the nine exact reference warm answers and Ornith’s three new warm answers. Twelve fresh scalar judgments and four rubric-triggered pairwise checks were frozen before revealing fresh candidate IDs. The interactive judge had prior answer/score and historical Ornith exposure plus visible orchestration: partial cognitive blinding, not independent blind evaluation. No paid judge API was used.

Scores use each task’s frozen 0–100 rubric. Reference score changes from the earlier report are evaluator variation on unchanged text, not fresh inference or model improvement. Small differences should not be treated as stable rankings.

| Task | Qwen 3.8 | Gemma 4 | Nemotron 3.5 Lightning | Ornith 1.5 |
| --- | ---: | ---: | ---: | ---: |
| Medical screening / Bayes | 85 | 84 | 81 | 65.5 |
| METR paper summary | 67 | 76.5 | 64.5 | 83 |
| Grounded LinkedIn writing | 59 | 61.5 | 44.5 | 75.5 |

- Ornith leads this summary and writing assessment. Its writing faithfully integrates the three personal thoughts, but still loses evidence coverage and overstates some source conclusions.
- Ornith’s Bayes arithmetic is correct, but its final mortality criterion reverses the required direction, and its false-negative label is wrong. Fluent prose and a correct numerical answer do not establish sound explanation.
- Qwen and Nemotron summaries inflate more than 800 human attempts into more than 800 distinct professionals. Gemma and Ornith avoid that unit error.
- Nemotron’s writing turns a measured 19% increase in implementation time into a productivity gain and misstates the instability finding. This saved answer remains an observed source-fidelity failure.
- The generic native `heading_pass = false` diagnostic for heading-free LinkedIn posts is preserved. The frozen writing rubric does not require headings; no heading-based score cap was added.

## Coding and agent outcomes

`pass` means full native deterministic verification. A fractional count preserves failed requirements; a failed task is still a completed measurement. Grounding and supplier language are reviewed separately below.

| Task / system | Qwen 3.8 | Gemma 4 | Nemotron 3.5 Lightning | Ornith 1.5 |
| --- | --- | --- | --- | --- |
| direct-coding | fail: malformed artifact | pass | fail: malformed artifact | fail: malformed artifact |
| mini-coding | pass | budget exhausted | fail: hidden tests failed | pass |
| pi-coding | pass | pass | pass | pass |
| mini-log | 13/15 checks | 11/15 checks | 10/15 checks | 11/15 checks |
| pi-log | 14/15 checks; transport failed | budget exhausted | budget exhausted | budget exhausted |
| mini-supplier | pass | 8/12 checks | 9/12 checks | 8/12 checks |
| pi-supplier | 11/12 checks | budget exhausted | 9/12 checks | 10/12 checks |

Ornith’s direct coding artifact is malformed, while both Mini and Pi pass public and hidden coding checks. All four Pi coding observations pass. Mini distinguishes the deployments: Qwen and Ornith pass; Gemma exhausts the 900-second active budget after repeated zero-match edits without writes; Nemotron fails hidden checks. These observations show a configuration-dependent result and do not isolate a single cause.

## Source grounding and output contract

The unblinded interactive review reads each final log/document report against the frozen sources. Supplier free text must be German under the existing task. Prose acceptance does not repair missing controlled codes or local evidence anchors, and native passes do not guarantee grounded prose. Missing final reports are not assessable rather than given a zero prose score.

| System | Model | Runtime | Strict transport | Native checks | Prose | Controller seconds |
| --- | --- | --- | --- | --- | --- | ---: |
| mini-log | Qwen 3.8 | pass | pass | 13/15 | pass | 62.2 |
| mini-log | Gemma 4 | pass | pass | 11/15 | pass | 102.5 |
| mini-log | Nemotron 3.5 Lightning | pass | pass | 10/15 | fail | 40.5 |
| mini-log | Ornith 1.5 | pass | pass | 11/15 | fail | 36.6 |
| pi-log | Qwen 3.8 | pass | fail | 14/15 | pass | 292.9 |
| pi-log | Gemma 4 | fail | fail | 0/1 | not assessable | 300.6 |
| pi-log | Nemotron 3.5 Lightning | fail | fail | 0/1 | not assessable | 300.8 |
| pi-log | Ornith 1.5 | fail | fail | 0/1 | not assessable | 301.1 |
| mini-supplier | Qwen 3.8 | pass | pass | 12/12 | fail | 125.1 |
| mini-supplier | Gemma 4 | pass | pass | 8/12 | pass | 108.3 |
| mini-supplier | Nemotron 3.5 Lightning | pass | pass | 9/12 | fail | 46.0 |
| mini-supplier | Ornith 1.5 | pass | pass | 8/12 | fail | 81.3 |
| pi-supplier | Qwen 3.8 | pass | pass | 11/12 | fail | 235.2 |
| pi-supplier | Gemma 4 | fail | fail | 0/12 | not assessable | 300.6 |
| pi-supplier | Nemotron 3.5 Lightning | pass | pass | 9/12 | fail | 149.4 |
| pi-supplier | Ornith 1.5 | pass | pass | 10/12 | pass | 140.9 |

New Ornith source-review findings:

- **mini-log:** Correctly identifies the +462-second host clock defect, admission trigger, first user impact and partial recovery. However, the reconciliation recommendation says 913 authorizations remain; the final source observation has 612 pending after 301 completions. The diagnosis gives payment-03 shutdown as 08:27:12Z without correcting its explicitly untrusted host clock. With the independently observed +462-second offset, this corresponds to approximately 08:19:30 UTC. The task requires report timestamps normalized to UTC. Native verification remains 11/15: causal_chain omits LB-201; the database rejection lacks DB-601 in its attached evidence; checkout_latency_increased is missing; provider_outage is not the allowed rejected-hypothesis code payment_provider_outage. Prose review changes no native outcome.
- **pi-log:** The episode read all seven source log files (eight reads, one repeated) and exhausted the 300-second active budget without a final assistant report. Prose is not assessable; no zero quality score is invented. Native runtime, valid termination and strict transport fail. The verifier can run only the missing-report schema check (0/1), which does not establish fifteen separate factual errors. Native output-token counters cover completed message events and are not a full count for an interrupted response.
- **mini-supplier:** The report reads the source values correctly but reverses the cost ranking: it calls Boreal at EUR 1,165,000 cheaper than Atlas at EUR 1,140,000, selecting Boreal primary and Atlas reserve. Atlas is also inconsistently listed as rejected for its assurance rating even while the explanation correctly says its final B rating is eligible. The action codes award_atlas and designate_boreal_reserve pass the native action check, but their free-text rationales explicitly call these codes wrong and recommend the reversed award. A controlled-code pass does not establish an internally consistent action plan. Draft versus signed-final status and cutoff are correctly distinguished. Most free text is German, but capacity headroom is repeatedly mislabeled utilization. The decisive prose failure is the reversed ranking and inconsistent supplier/action fields, not a German-language violation. Native verification remains 8/12: primary, reserve, supplier blockers and conflict resolution fail. Required evidence and citation integrity pass; the dashboard conflict mentions policy in prose but omits the mandatory policy authority anchor from its local source_refs. No native result is changed.
- **pi-supplier:** Correct Atlas primary at EUR 1,140,000 and Boreal reserve at EUR 1,165,000, with the correct Cedar critical-finding and Delta 12-percent headroom exclusions. The unsigned draft, signed final, signature time and decision cutoff are correctly distinguished. Free text is predominantly German with awkward mixed terminology. The dashboard resolution contains a double negative but immediately and repeatedly states the correct rule that commercial ranking cannot replace eligibility checks. The future-evidence action should more explicitly name a new decision cycle; it does not assert that post-cutoff evidence changes the frozen award. These imprecisions do not reverse the source-grounded decision. Native verification remains 10/12: required evidence omits BID-CEDAR; local conflict anchors omit the signed-final note in draft supersession and policy authority in the dashboard conflict. Those facts appear elsewhere, but prose acceptance does not supply the missing locally required anchors or complete the native task.

The twelve preserved reference reviews are documented in the previous report and retained in this JSON. In particular, Qwen’s supplier prose calls an unsigned draft signed even where native checks pass; Nemotron’s supplier free text violates the German requirement. Source authority, final observed state and language remain useful repeat-study targets.

## Timings and limits

Text values are native client wall seconds for one cold/warm pair per task. Warm answers alone are quality candidates. References retain their earlier timings; they were not remeasured for this extension. One pair does not establish a stable latency distribution.

| Text task | Model | Cold seconds | Warm seconds | Warm output tokens/s |
| --- | --- | ---: | ---: | ---: |
| Medical screening / Bayes | Qwen 3.8 | 63.0 | 52.0 | 22.2 |
| Medical screening / Bayes | Gemma 4 | 59.3 | 51.5 | 18.4 |
| Medical screening / Bayes | Nemotron 3.5 Lightning | 21.9 | 11.4 | 105.4 |
| Medical screening / Bayes | Ornith 1.5 | 13.6 | 12.7 | 89.5 |
| METR paper summary | Qwen 3.8 | 110.0 | 121.5 | 14.5 |
| METR paper summary | Gemma 4 | 137.3 | 70.8 | 16.5 |
| METR paper summary | Nemotron 3.5 Lightning | 38.8 | 13.1 | 99.5 |
| METR paper summary | Ornith 1.5 | 33.3 | 18.9 | 90.2 |
| Grounded LinkedIn writing | Qwen 3.8 | 69.4 | 33.4 | 22.5 |
| Grounded LinkedIn writing | Gemma 4 | 78.6 | 37.9 | 17.4 |
| Grounded LinkedIn writing | Nemotron 3.5 Lightning | 19.2 | 10.5 | 102.2 |
| Grounded LinkedIn writing | Ornith 1.5 | 20.7 | 16.6 | 48.1 |

| Coding system | Model | Controller seconds | Recorded provider requests |
| --- | --- | ---: | ---: |
| direct-coding | Qwen 3.8 | 31.0 | 1 |
| direct-coding | Gemma 4 | 42.3 | 1 |
| direct-coding | Nemotron 3.5 Lightning | 24.8 | 1 |
| direct-coding | Ornith 1.5 | 27.0 | 1 |
| mini-coding | Qwen 3.8 | 69.8 | 17 |
| mini-coding | Gemma 4 | 943.9 | 95 |
| mini-coding | Nemotron 3.5 Lightning | 40.3 | 19 |
| mini-coding | Ornith 1.5 | 36.3 | 18 |
| pi-coding | Qwen 3.8 | 100.6 | unknown |
| pi-coding | Gemma 4 | 258.3 | unknown |
| pi-coding | Nemotron 3.5 Lightning | 199.5 | unknown |
| pi-coding | Ornith 1.5 | 101.7 | unknown |

Known provider-request subtotal: 274 across 28/40 cells. All 12 Pi HTTP counts and the full total remain unknown; agent turns are not request counts. Interrupted responses may lack final usage events. Supplier operations use normalization 0.2.0; native tool counters across harnesses are not pooled as an efficiency score.

Controller timings exclude preparation, resource/sandbox gates and unload, but include native execution, verification and CLI orchestration. Native active/provider timings remain separate in the JSON. Agent budgets remain 900 active seconds for coding and 300 for logs/documents; provider limits remain 300 and 180 seconds respectively. No attempt was restarted.

Environment: Apple M4 Max, 64 GiB RAM, 16 logical CPUs, `Mac16,5`; Darwin 25.1.0, Python 3.14.4, Node v22.22.1, coding PHP 8.4.17, Ollama 0.40.5. Empty artifact metadata stays unknown rather than inferred from tags.

The extension binds 410 source files, including additive coverage reader 0.3. All 409 previous sources and all native reference hashes validate. Eight fresh resource gates, three Pi sandbox acceptances and eight empty unload postflights cover the new native blocks. Thirteen new native records join thirty-nine preserved references; native records and earlier scores were not rewritten.

Extension plan SHA-256: `2074a2ed6c289d0d1356c488c6114990d3cf037c82875d8abc578f089eba1901`. Reference plan: `6dbee7eb595c5daf06a368eab91ab79b8c2635c56647807036edfd67c3305590`.

New scalar freeze: `dd361bd798eee9bd80fa64e96ab91be577113cafbbf0d856377b9d2784ca1ffd`. Pairwise freeze: `c4ac22a921c00b72ef4e5eadbe740fafd29a71c4cdd2d3b32a2460bc902f2a6a`.

## Selected follow-up questions

- First repeat only two text comparisons: Bayes with Ornith versus Qwen, and grounded writing with Ornith versus Nemotron. Three independent observations per selected cell would test the specific errors and task tradeoff in a fresh shared judgment batch; this remains too small for precise reliability probabilities.
- Repeat the existing coding fixture with Mini and Pi, prioritizing Nemotron hidden-test behavior and Gemma failed-edit recovery; change harness versions only in a separate experiment.
- Repeat supplier/log cells selectively to test source-status, final-state and language errors. Preserve the 300-second budget before testing a separately versioned budget or prompt change.

These are selected follow-up questions, not additional executions in this extension. Keep changed prompts, budgets or harnesses in separately versioned experiments. The 23-case inventory remains provisionally closed; structured extraction and normalization stays in the next suite version.
