# General knowledge benchmark

This track measures whether a local model can answer and explain a knowledge
question from its internal knowledge. Candidate models do not receive sources
and may not browse. The interactive judge receives a frozen reference dossier
compiled from authoritative sources.

This is not a trivia benchmark. A good answer must select the important facts,
explain the causal or conceptual structure, avoid common misconceptions and
communicate uncertainty precisely to an informed non-specialist.

## Development pilot

The first pilot deliberately spans three domains:

- `confidence-intervals`: statistical interpretation and conceptual precision
- `mrna-vaccine-mechanism`: scientific explanation and misconception handling
- `interest-rates-and-inflation`: causal economic reasoning and trade-offs

The pilot also contains one deliberately harder companion:

- `confidence-intervals-transfer`: transfer of statistical concepts to a
  conflict between a large observational study and a smaller randomized study

The transfer case does not replace the foundation confidence-interval item.
The foundation item measures conceptual correctness and completion reliability;
the companion tests whether a model can combine precision, systematic bias,
causal strength, statistical significance and practical relevance in a new
decision scenario.

These are development cases. Their prompts, reference dossiers and rubrics may
be improved after inspecting results, but any change must increment the
relevant version. Future holdout cases must remain private until the method is
frozen.

## Hard Knowledge v0.2

A second block was frozen in full before any of its model runs. It adds six
hard transfer cases:

- `medical-screening-bayes`: natural frequencies, base rates and misleading
  screening outcome measures
- `antibiotic-resistance`: evolution, horizontal gene transfer, transmission
  and stewardship
- `renewable-electricity-matching`: annual accounting, hourly balancing and
  flexibility across timescales
- `distributed-payment-reliability`: failure boundaries, idempotency, outbox
  and reconciliation
- `ml-evaluation-leakage`: preprocessing leakage, model-selection bias and
  nested cross-validation
- `rag-grounding-evaluation`: retrieval failures, claim-level grounding and
  citation evaluation

The versioned manifest freezes their order, the four deployment aliases, fixed
inference settings, environment gate, adaptive repetition rule and aggregate
policy. It also balances within-case model position: every deployment occurs
once or twice in each of the four positions across the six cases. See
[`hard-knowledge-v0.2.json`](hard-knowledge-v0.2.json) and
[`docs/hard-knowledge-v0.2.md`](../../docs/hard-knowledge-v0.2.md).

## Source separation

Every case declares `source_delivery: judge_only`. The runner verifies the
reference dossier hash and packages it for judgment, but never injects it into
the candidate request. This preserves the distinction between general
knowledge and source-grounded synthesis.

The dossiers are concise, project-authored summaries of their cited sources,
not copies of source publications. Source IDs such as `[S01]` exist only for
evaluation traceability and must never appear in a candidate answer.
