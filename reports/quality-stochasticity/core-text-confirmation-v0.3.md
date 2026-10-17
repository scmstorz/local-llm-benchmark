# Selected core text confirmation v0.3

Twelve fresh warm answers confirm the task-specific contrast seen in the core
screen: Qwen is preferred in all three Bayes pairs, and Ornith in all three
grounded-writing pairs. Ornith repeats its two material Bayes errors in three
byte-identical answers. Nemotron repeats the reversed productivity finding in
two writing answers; the third avoids that error but remains less complete.

All twelve cold/warm pairs completed on 2026-10-17 under Ollama 0.40.5. There
were twenty-four native generations, zero retries, twelve clean resource gates
and twelve empty postflights. Earlier answers and scores remain separate and
unchanged. [Machine-readable results](core-text-confirmation-v0.3.json) and
[frozen protocol](../../docs/quality-confirmation-v0.3.md).

## Fresh observations

| Task | Deployment | Scores by repetition | Median | Range | Pair W-L-T | Distinct answers |
| --- | --- | --- | ---: | --- | --- | ---: |
| Bayes | Qwen 3.8 MLX | 85, 85, 85 | 85 | 85–85 | 3-0-0 | 2/3 |
| Bayes | Ornith 1.5 GGUF/Q4_K_M | 68.5, 68.5, 68.5 | 68.5 | 68.5–68.5 | 0-3-0 | 1/3 |
| Grounded writing | Ornith 1.5 GGUF/Q4_K_M | 76, 76, 76 | 76 | 76–76 | 3-0-0 | 1/3 |
| Grounded writing | Nemotron 3.5 Lightning MLX | 43.5, 47.5, 58.5 | 47.5 | 43.5–58.5 | 0-3-0 | 3/3 |

Scores use the existing task-specific rubrics. Equal scores do not imply equal
text: Qwen has two distinct Bayes answers with equivalent judged quality.
Conversely, Ornith's three identical answers on each task are repeated
generations, not three independent text variants or independent judge opinions.
A rubric verdict such as `usable` is a score band, not a statement that an
answer contains no material factual error.

## What repeated and what changed

**Bayes:** All six answers calculate the natural-frequency table and positive
predictive value correctly. In all three Ornith answers, however, a false
negative is also called a true negative, and the final conclusion reverses the
mortality criterion for demonstrating screening benefit. The same answer
reappears byte-for-byte across its three fresh repetitions. These observations
do not support the hypothesis that the earlier wording errors would disappear
on this small fixed-setting repeat.

Qwen avoids both of those errors in all three observations and is preferred in
every paired judgment. Its explanations still omit a clear confirmatory
clinical pathway and parts of the broader outcome/follow-up framework. Minor
sensitivity wording and slow-disease imprecisions remain. This is a stronger
observed explanation on this case, not a universal knowledge ranking.

**Grounded writing:** All three Ornith outputs are the same 431-word post. It
correctly reports the 19-percent increase in implementation time, integrates
all three user thoughts and distinguishes occasional task completion from
dependable autonomy. It still incompletely covers verification economics,
historical/external-validity limits and the human-duration definition of the
horizon. Its opening overstates what benchmark success establishes about
production readiness, and it too narrowly attributes a full-interface result
to the editor.

Nemotron produces three different posts of 266, 335 and 289 words. The first
two again turn the randomized 19-percent completion-time increase into a
productivity increase. Both also misstate the post-study perceived gain. The
second adds causal DORA wording and an unsupported burnout connection. The
third correctly describes a qualitative slowdown, so the direction error is
not present in every fresh answer. Nevertheless, it omits the horizon evidence,
weakens the task-dependent-supervision thought and retains imprecise DORA
framing. All three posts fall below the requested 400–550-word target; this is
a format-quality deduction, not a hard-limit invalidation. Ornith is preferred
in every writing pair, including the third.

The writing comparison deliberately tests a previously observed source-fidelity
contrast. It does not establish Ornith as the best of all available writing
deployments, because Qwen and Gemma are not repeated on this task here.

## Execution, diagnostics and timing

Each quality candidate immediately follows a fresh cold answer to the same
task. All twenty-four native request payloads match their exact earlier
model/task condition, including the rendered messages and generation settings.
Temperature remains zero, seed 42, context 8,192 tokens, output limit 2,600,
thinking disabled and timeout 600 seconds. Model digests, templates, parameters,
hardware and runtime match the corresponding earlier records. All 411 bound
source hashes remain valid. No consumer was stopped.

All twelve measured answers satisfy the applicable native language, nonempty,
length, source-label, completion and reasoning-markup checks; all six Bayes
answers also satisfy the heading check. The generic pipeline additionally
requires `heading_pass` in its all-checks statistic, yielding zero for the
heading-free writing posts. That unchanged diagnostic is retained in JSON.
The writing rubric requires no headings, so no heading-based penalty or cap is
applied; the task-aware applicable-check count is reported separately. Neither
diagnostic passing nor technical completion establishes source fidelity.

| Task / deployment | Median warm client wall time |
| --- | ---: |
| Bayes / Qwen 3.8 MLX | 33.04 s |
| Bayes / Ornith 1.5 | 11.56 s |
| Writing / Ornith 1.5 | 9.32 s |
| Writing / Nemotron 3.5 Lightning MLX | 5.70 s |

These are descriptive warm-generation times for three natural-length outputs.
They exclude cold companions, resource gates and unload. No tail-latency,
controlled decode-speed or precise reliability claim is supported.

## Evaluation and interpretation limits

Six fresh opaque candidates per case were assessed against the unchanged
source dossier/packet, personal thoughts and rubric. All twelve scalar results
passed their case-specific schema and arithmetic checks and were frozen before
any pair review. All six predeclared same-repetition pairs were then frozen
before either current mapping was opened. The native joins and aggregates
reproduce exactly; no old scalar result was copied and no frozen score was
rewritten. No paid judge API was used.

Blinding is explicitly partial: the interactive judge had seen prior answers,
scores and error hypotheses, and orchestration was visible. Procedural freezes
do not establish independent cognitive blinding. Recognition of repeated text
is possible. Newly assigned scores for text that matches an older answer do
not measure an improvement or decline in model behavior.

Three fixed-seed observations per condition test operational repeatability.
They are too few for rare-failure probabilities and are not independent random
draws across seeds or temperatures. The results support task-bound selection
and concrete recurring-error findings, not a cross-task composite ranking.
The next development question can therefore focus on separately versioned
Mirror/Vibe systems using existing agentic cases, while preserving this study.

## Provenance

- Parent plan SHA-256: `2d552c728d735c13b1af7939169adb6e2ce08300771ff91bf2fc4aa3b4f48f5d`
- Bayes scalar freeze: `6431ebdc493002b934b4eac01417f733f84c1dd9938b8b251e08461d013153b1`
- Bayes pair freeze: `36c12b58783876df7c9d5cd0dbbfb5d8b7a36704b91025d166b4e86f351c2bb0`
- Writing scalar freeze: `37f3ce7df3972f74bc3e8452adf3561a731f513ce90098c30cf61414cfae32e0`
- Writing pair freeze: `36b3345c99f0680132d2b3d70c1e7a082147a5c62fb40091854d43a5a6810d8e`

Private requests, streams, responses, judge records, maps and integrity proofs
remain local and are excluded from public export.
