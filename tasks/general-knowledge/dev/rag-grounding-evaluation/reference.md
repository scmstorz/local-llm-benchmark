# Frozen reference dossier: grounding and evaluating a RAG system

Retrieved: 2026-08-29

[S01] Retrieval-augmented generation (RAG) combines a retriever with a language
model so the model can condition an answer on passages from an external corpus.
It can make knowledge updateable and provide provenance without encoding every
fact in model parameters. It does not force the generator to use only retrieved
evidence or guarantee that the retrieved material is relevant, complete or
correct.

Source: Lewis et al., “Retrieval-Augmented Generation for Knowledge-Intensive
NLP Tasks”  
https://arxiv.org/abs/2005.11401

[S02] Failure can occur before generation. The corpus may lack the answer;
chunking can split necessary context; indexing or metadata filters can exclude
it; a query may be underspecified; embedding retrieval can miss relevant text;
or top-k can return plausible distractors. A fluent answer cannot reveal which
stage failed. Retrieval must therefore be evaluated independently with labeled
relevance or answer evidence, using measures such as recall at k.

This systems analysis is project-authored from [S01] and [S05].

[S03] Even when the needed passage is present, a model may ignore it, combine
it incorrectly, add unsupported claims from parametric memory, or follow a
conflicting distractor. Long-context models do not use every position equally;
experiments show performance can decline when relevant evidence is buried in
the middle. More retrieved text can consequently add noise as well as recall.

Source: Liu et al., “Lost in the Middle: How Language Models Use Long Contexts”  
https://arxiv.org/abs/2307.03172

[S04] An answer can be factually true yet unsupported by the provided corpus,
or fully supported by poor or outdated evidence. Evaluation should separately
ask whether each material claim is entailed by cited passages (citation
correctness or precision), whether all claims that need support have evidence
(citation completeness or recall), and whether the answer actually answers the
question correctly and completely.

Source: Gao et al., “Enabling Large Language Models to Generate Text with
Citations” (ALCE)  
https://aclanthology.org/2023.emnlp-main.398/

[S05] RAGTruth documents unsupported and contradictory claims in RAG outputs
and distinguishes error types at span level. Retrieval reduces some knowledge
failures but does not eliminate hallucination. Aggregate answer correctness
alone can hide unsupported details, so claim-level attribution and adversarial
cases are valuable.

Source: Niu et al., “RAGTruth: A Hallucination Corpus for Developing
Trustworthy Retrieval-Augmented Language Models”  
https://aclanthology.org/2024.acl-long.585/

[S06] A useful test set isolates stages: answerable and unanswerable questions;
gold evidence present versus absent; relevant passages at different ranks or
positions; near-duplicate and contradictory distractors; multi-hop questions;
fresh documents; and permission-filtered cases. Component metrics include
retrieval recall and ranking, while end-to-end metrics cover answer correctness,
claim-level groundedness, citation quality, abstention and latency. Exact-match
scores alone are insufficient for explanatory answers.

This evaluation design is project-authored from [S02] through [S05].

[S07] Mitigations act at different stages: improve corpus and chunking; combine
sparse and dense retrieval, metadata filters or reranking; rewrite or decompose
queries; limit and order context; require claim-level citations; instruct the
model to abstain when evidence is missing; verify generated claims; and expose
retrieved evidence for audit. Each adds cost or latency and must be tested.
Because abstention itself can be too frequent or misplaced, it needs precision
and recall-like evaluation rather than being assumed safe.

This systems synthesis is project-authored from [S01] through [S06].
