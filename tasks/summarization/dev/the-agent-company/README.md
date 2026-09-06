# TheAgentCompany - development case

Case ID: `summarization.dev.the-agent-company`

This is the second article-summarization development case. It tests whether a
local model can turn a substantial English research paper into a clear,
source-faithful German summary for an informed non-specialist reader.

The case is classified as `hard`: the input is roughly 6,000 words and combines
benchmark motivation, environment design, metrics, experimental results,
authors' interpretations and explicit limitations. Unlike the first development
article, it has no publisher-written key-findings section.

## Frozen source scope

The input is arXiv version 3 of *TheAgentCompany: Benchmarking LLM Agents on
Consequential Real World Tasks* (`arXiv:2412.14161v3`, dated 2025-09-10), a paper
published in the NeurIPS 2025 Datasets and Benchmarks Track.

The cleaned input includes:

- title and authors
- abstract
- Sections 1 through 8
- the Figure 1 caption
- Table 1 in text form

It excludes references, acknowledgments, appendices and figure image data. This
keeps the case focused on research-paper summarization rather than making it a
separate full-document context-scaling experiment. The arXiv PDF was visually
checked against the extracted source, especially the main result table and the
boundary between the main paper and references. The final NeurIPS proceedings
PDF was also inspected and stored privately as a verification artifact, but it
is not silently substituted for the explicitly frozen arXiv v3 input.

## Private source

The source artifacts are stored under:

```text
data/private/summarization/dev/the-agent-company/
```

They remain Git-ignored. `source-metadata.json` freezes the exact PDF version,
scope, extraction process and SHA-256 hashes. Stable `[P01]` through `[P31]`
location labels were added only to support judge evidence; candidates must not
copy them.

## Context requirement

This case requires at least a 16,384-token context window. The runner rejects a
smaller configured context before contacting Ollama.

Run one model without a warm-up:

```bash
python3 -m local_llm_benchmark run \
  --model qwen3.6:35b-a3b-mxfp8 \
  --case tasks/summarization/dev/the-agent-company/case.json \
  --num-ctx 16384
```

For a cold/warm comparison, pass the same `--case` and `--num-ctx 16384`
arguments to `compare`. Before any performance comparison, follow the mandatory
application-stop and Ollama preflight gate in `PROJECT_STATUS.md`.
