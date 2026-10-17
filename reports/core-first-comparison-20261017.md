# First core comparison: Qwen, Gemma and Nemotron

Thirty task/system/model cells completed on 2026-10-17, using three installed MLX deployments under Ollama 0.40.5. This comparison uses six representative tasks from the provisionally closed 23-case inventory. Each cell is one observation; the text cells additionally retain one cold request before the scored warm request. No benchmark attempt was restarted and no historical observation was reused.

This is a capability screen of deployed systems. Quality scores, deterministic checks, protocol compliance, runtime completion and prose accuracy answer different questions and remain separate. There is no combined model score or reliability estimate.

Machine-readable evidence, exact deployment digests, native counters and record hashes: [comparison JSON](core-first-comparison-20261017.json). Selected deployments: [cohort](../models/cohorts/core-first-comparison-2026-10-17.json).

## Text quality

Scores use each case's frozen rubric, on a 0–100 scale. Nine independent scalar judgments and two conditionally required Bayes pairwise checks were frozen before the candidate map was revealed. The interactive judge had seen orchestration progress and some timing metadata; this was partial blinding, not an independent blind evaluation. No paid judge API was used.

| Task | Qwen 3.8 | Gemma 4 | Nemotron 3.5 Lightning |
| --- | ---: | ---: | ---: |
| Medical screening / Bayes | 82.5 | 85.5 | 79.5 |
| METR paper summary | 67.5 | 78.5 | 61.5 |
| Grounded LinkedIn writing | 63.5 | 59 | 45 |

- All three calculate the medical screening positive predictive value correctly. Their explanations still omit some decision and evidence limits.
- Qwen and Nemotron turn more than 800 human baseline attempts into more than 800 distinct professionals in the METR summary. Gemma avoids this unit error.
- Nemotron's writing reverses a randomized 19% increase in implementation time into a productivity gain, and contradicts itself on delivery instability. Gemma's opening conflicts with its later verification requirement. Qwen preserves the slowdown but overstates causal and organizational evidence.
- The generic native checker marks heading-free LinkedIn posts `heading_pass = false`. The frozen writing rubric requires a post with short paragraphs, not headings. The raw diagnostic is preserved; it adds no heading-based quality cap.

## Coding and agent outcomes

`pass` means full native deterministic verification; a fractional check count means required checks failed. A failed task remains a completed observation. For logs and supplier documents, prose grounding and language are reviewed separately below.

| Task / system | Qwen 3.8 | Gemma 4 | Nemotron 3.5 Lightning |
| --- | --- | --- | --- |
| direct-coding | fail: malformed artifact | pass | fail: malformed artifact |
| mini-coding | pass | budget exhausted | fail: hidden tests failed |
| pi-coding | pass | pass | pass |
| mini-log | 13/15 checks | 11/15 checks | 10/15 checks |
| pi-log | 14/15 checks; transport failed | budget exhausted | budget exhausted |
| mini-supplier | pass | 8/12 checks | 9/12 checks |
| pi-supplier | 11/12 checks | budget exhausted | 9/12 checks |

The coding contrast is already useful: Qwen fails the one-shot artifact envelope but passes with both agents. Gemma passes directly and with Pi, yet its Mini episode exhausts the 900-second active budget after repeated zero-match text replacements, without writing a file. The native Mini failure category is retained; the trajectory shows ineffective action recovery rather than proof of an external outage. These observations do not isolate the cause to a model or harness alone.

## Log and supplier source review

The unblinded interactive source review reads each final report against the frozen source facts and checks the supplier task's explicit German free-text requirement. Prose acceptance concerns grounding and language; missing controlled fields remain native completeness failures. It does not change native verification. Missing final reports are not assessable, rather than assigned a prose score. Supplier verification uses version 2.1.0 / evaluation contract 0.3; normalized operation counters use metrics 0.2.

| System | Model | Runtime | Strict transport | Native checks | Prose | Controller seconds |
| --- | --- | --- | --- | --- | --- | ---: |
| mini-log | Qwen 3.8 | pass | pass | 13/15 | pass | 62.2 |
| mini-log | Gemma 4 | pass | pass | 11/15 | pass | 102.5 |
| mini-log | Nemotron 3.5 Lightning | pass | pass | 10/15 | fail | 40.5 |
| pi-log | Qwen 3.8 | pass | fail | 14/15 | pass | 292.9 |
| pi-log | Gemma 4 | fail | fail | 0/1 | not assessable | 300.6 |
| pi-log | Nemotron 3.5 Lightning | fail | fail | 0/1 | not assessable | 300.8 |
| mini-supplier | Qwen 3.8 | pass | pass | 12/12 | fail | 125.1 |
| mini-supplier | Gemma 4 | pass | pass | 8/12 | pass | 108.3 |
| mini-supplier | Nemotron 3.5 Lightning | pass | pass | 9/12 | fail | 46.0 |
| pi-supplier | Qwen 3.8 | pass | pass | 11/12 | fail | 235.2 |
| pi-supplier | Gemma 4 | fail | fail | 0/12 | not assessable | 300.6 |
| pi-supplier | Nemotron 3.5 Lightning | pass | pass | 9/12 | fail | 149.4 |

Source-review findings:

- **Gemma 4 / mini-log:** Correctly identifies the +462-second clock defect, node admission trigger, first user impact and only partial recovery with 612 pending. No material contradictory or unsupported prose claim found. Native verification is 11/15: the causal chain omits LB-201, PAY3-300 and EDGE-403; alternative rejection lacks required attached counter-evidence; the latency impact code and two material uncertainty codes are absent. Prose acceptance does not repair these failures.
- **Nemotron 3.5 Lightning / mini-log:** Correct root clock offset and partial-recovery category, but the recommendation says 913 authorizations remain, contradicting the final observation of 612 pending after 301 completions. The provider rejection reason claims PROV-501 proves another trace succeeded and that only pay-77 was affected. PROV-501 instead records pay-77 never received; neither exclusivity nor this attached proof is supported. Native verification is 10/15: causal ordering, evidence roles, attached alternative counter-evidence, bounded impact and material uncertainties fail. The prose rejection is separate from those deterministic failures.
- **Qwen 3.8 / mini-log:** Coherent grounded clock-skew diagnosis, causal sequence, source-attached rejection of provider/database alternatives, and explicit distinction between recovered new requests and the final 612-pending backlog. No material prose contradiction found. Native verification remains 13/15: the REC-700 backlog-creation impact evidence role and payment_data_loss_unknown uncertainty code are missing. Correct prose does not supply those omitted machine-scored fields.
- **Nemotron 3.5 Lightning / pi-log:** The episode read all seven log files but exhausted the 300-second active limit without a final assistant response/report. No prose exists to review; this is not a zero quality score. Native runtime/termination and strict transport fail. The deterministic verifier receives no report; its failed checks do not establish which source facts the model would have reported.
- **Qwen 3.8 / pi-log:** The native extracted report is source-grounded: host-specific skew, exposing admission, sampled impact, alternative causes, final 612-pending partial recovery and four material uncertainties are correctly distinguished. No material prose contradiction found. Native semantics remain 14/15 because the causal_chain omits LB-201 and EDGE-403 even though they appear elsewhere. Strict transport fails because the raw response adds an introductory sentence; the frozen normalizer extracts JSON without converting that into strict compliance.
- **Gemma 4 / pi-log:** Read all seven log files but exhausted the 300-second active limit without a final response/report. Prose is not assessable and receives no scalar quality score. Native runtime/termination and strict transport fail. Only the schema/no-report check can run; this is not evidence of fifteen separately diagnosed factual errors.
- **Qwen 3.8 / mini-supplier:** Native verification is 12/12 with strict transport and correct Atlas primary/Boreal reserve, supplier blockers, cost/headroom arithmetic and required actions/uncertainties. The draft conflict explicitly calls page 2 a signed draft even though its attached Unsigned-draft source and the report’s own evidence say it is unsigned. This materially misstates the evidence status. The executive summary also calls 14:30 the cutoff, while policy and later actions use 16:00; 14:30 is final signature time. Prose fails without changing any native pass.
- **Gemma 4 / mini-supplier:** Source-supported Atlas primary/Boreal reserve, correct costs and Cedar/Delta blockers. Delta is called eligible in its assurance-only evidence entry but is correctly excluded for capacity in the decision and summary; the gate-local wording is imprecise, without reversing the overall decision. Native verification remains 8/12: required evidence is incomplete; draft supersession is absent; the dashboard conflict lacks required authority/scope anchors; future reassessment and the required post-cutoff/capacity uncertainties are missing. Prose accuracy acceptance does not mean a complete task solution.
- **Nemotron 3.5 Lightning / mini-supplier:** Correct Atlas/Boreal decision, blockers and main numerical values, but the draft-conflict prose says all draft supplier ratings are C or A; Delta is B in the supplied draft. The capacity rationale attributes the 15% threshold partly to a commercial-scope disclaimer that does not establish that threshold. All free text is English despite the explicit German-output task requirement; this adherence failure is not checked by the native controlled-value verifier. Native verification remains 9/12: required evidence is incomplete; conflicts omit required final-signature/policy anchors locally; future reassessment is absent. No native score is changed.
- **Gemma 4 / pi-supplier:** Completed 17 artifact operations (inventory, 4 DOCX, 6 PDF, 6 XLSX) but exhausted the 300-second active limit without calling finish_report. There is no final structured report to review. Native runtime/termination and strict transport fail; the native missing-report result is 0/12. That does not diagnose twelve independently observed factual mistakes, and no prose quality score is invented.
- **Nemotron 3.5 Lightning / pi-supplier:** Correct source-grounded Atlas/Boreal award, costs, blockers and unsigned-draft/signed-final distinction; no material reversed source fact found. Both conflict resolutions and several complete policy-support entries are English, while the frozen task requires German free-text values. The mixed-language prose therefore fails the explicit language constraint; this is separate from factual grounding. Native verification is 9/12: required evidence is incomplete; local conflict anchors omit the final-signature note and dashboard scope; future reassessment is absent. Strict transport passes, and no native score is changed.
- **Qwen 3.8 / pi-supplier:** Correct Atlas/Boreal award, costs, blockers, cutoff/signature times, actions and uncertainties. Native verification is 11/12: the dashboard conflict omits its mandatory local policy authority anchor, despite citing it elsewhere. Strict transport passes. The draft conflict, draft evidence support and executive summary repeatedly call the explicitly unsigned page 2 draft signed. This materially misstates evidence authority and fails prose grounding; no native result is changed.

## Timing and measurement limits

Text timings below are native client wall seconds for the preserved cold and warm requests. With one pair, they describe these executions and do not establish stable latency distributions. Each agent starts after a fresh empty-model gate; the controller duration includes its native execution, verification and CLI orchestration, while excluding preparation, the resource/sandbox gate and model unload. Native active seconds remain a separate field in the JSON.

| Text task | Model | Cold seconds | Warm seconds | Warm output tokens/s |
| --- | --- | ---: | ---: | ---: |
| Medical screening / Bayes | Qwen 3.8 | 63.0 | 52.0 | 22.2 |
| Medical screening / Bayes | Gemma 4 | 59.3 | 51.5 | 18.4 |
| Medical screening / Bayes | Nemotron 3.5 Lightning | 21.9 | 11.4 | 105.4 |
| METR paper summary | Qwen 3.8 | 110.0 | 121.5 | 14.5 |
| METR paper summary | Gemma 4 | 137.3 | 70.8 | 16.5 |
| METR paper summary | Nemotron 3.5 Lightning | 38.8 | 13.1 | 99.5 |
| Grounded LinkedIn writing | Qwen 3.8 | 69.4 | 33.4 | 22.5 |
| Grounded LinkedIn writing | Gemma 4 | 78.6 | 37.9 | 17.4 |
| Grounded LinkedIn writing | Nemotron 3.5 Lightning | 19.2 | 10.5 | 102.2 |

| Coding system | Model | Controller seconds | Recorded provider requests |
| --- | --- | ---: | ---: |
| direct-coding | Qwen 3.8 | 31.0 | 1 |
| direct-coding | Gemma 4 | 42.3 | 1 |
| direct-coding | Nemotron 3.5 Lightning | 24.8 | 1 |
| mini-coding | Qwen 3.8 | 69.8 | 17 |
| mini-coding | Gemma 4 | 943.9 | 95 |
| mini-coding | Nemotron 3.5 Lightning | 40.3 | 19 |
| pi-coding | Qwen 3.8 | 100.6 | unknown |
| pi-coding | Gemma 4 | 258.3 | unknown |
| pi-coding | Nemotron 3.5 Lightning | 199.5 | unknown |

The recorded provider-request subtotal is 223, covering 21/30 cells. The full-round total is unknown because Pi records agent turns, not provider HTTP requests. Unknown counts are not zero. Pi token usage summarizes completed messages; a budget-interrupted response may lack a final usage event, so its native counter is not claimed as a complete token total. Supplier artifact operations and report completion are normalized separately; native tool-call counters across harnesses are not pooled as an efficiency score.

Environment: Apple M4 Max, 64 GiB RAM, 16 logical CPUs, hardware identifier `Mac16,5`; Darwin 25.1.0, Python 3.14.4, Node v22.22.1, coding PHP 8.4.17, Ollama 0.40.5. No hostname or serial was collected.

Coverage uses the additive [reader 0.3](../docs/core-records-v0.3.md); all 409 bound source files remained unchanged. Fresh 30-second resource checks preceded every native block, and each Pi attempt passed its sandbox acceptance. Every native block unloaded its own model and recorded an empty postflight. The unchanged plan was bound to source commit `4339700aa64626ab76afe7e46d0e86f266c1d910` with SHA-256 `6dbee7eb595c5daf06a368eab91ab79b8c2635c56647807036edfd67c3305590`.

The original reader, tasks, harnesses and raw observations were preserved. An additive observer recognizes native immediately verified direct-coding records. A private controller completion-shape correction was applied before any coding inference; it did not restart an attempt or change a model-facing input. Text-evaluation format/path bookkeeping issues were resolved by preserving the original results and independently verifying all frozen/revealed hashes and reproduced aggregates.

A follow-up can register a new model or a separately versioned harness against the same task profile. Structured extraction and normalization remains deferred to the next suite version. Repeated trials and additional tasks are needed before claiming reliability or broad model superiority.
