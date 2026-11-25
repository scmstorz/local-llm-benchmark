# Explicit backend qualification for Mirror and Vibe v0.3

The separately versioned provider/scratch condition qualifies successfully.
All three short Qwen backend probes pass: no returned thinking, context16384
observed in Ollama after every response, correct text, correct tool call and
correct tool-result replay. Ollama is empty afterwards. No coding task was
rerun, and this is not a new speed comparison.

The [machine-readable report](external-cli-effective-backend-v0.3.json) records
the result; the [method](../../integrations/external-cli-v0.3.md) and
[contract](../../tasks/coding/track-b/external-cli-v0.3.json) specify the condition.
Source freeze: `df87ba25739cbe5017af5da357739025d4bcd90f`.
Runtime: Ollama0.40.5, `qwen3.8:27b-mlx`.

| System/condition | Effective control evidence | Remaining comparison limitation |
| --- | --- | --- |
| Mini v0.3 | Its actual native request builder sends thinking off, backend context16384, temperature0, seed42 and output ceiling1600. | This audit is of construction; no new Mini model run. |
| Pi v0.3 | Actual pinned CLI stub request sends temperature0, seed42 and max_completion_tokens1600. | Thinking-off and backend-context controls are absent; client context declarations do not establish allocation. |
| Mirror v0.3 | Native CLI tool/final/deadline qualification plus the explicit backend bridge. Both wire sides retained. | New condition; no new live coding outcome. |
| Vibe v0.3 | Same qualification and bridge. Explicit output cap also covers legacy requests and context summaries. | New condition; no new live coding outcome. |

The bridge sends native thinking off, temperature0, seed42, context16384 and
at most1600 output tokens on every request, including compaction. Smaller CLI
ceilings remain honored. These are explicit requested settings; seed/temperature
transmission alone is not a statistical reproducibility result. The installed
Qwen model declares medium as its default thinking level, so omission of the
off control matters. Native [thinking/options](https://docs.ollama.com/api/chat)
and [tool-result replay](https://docs.ollama.com/capabilities/tool-calling)
follow Ollama's documented API. The bridge is an explicit provider adaptation
and therefore part of this new complete-system condition.

| Short backend probe | Client response | Effective output cap | Observed output tokens | Thinking characters | Observed context |
| --- | --- | ---: | ---: | ---: | ---: |
| Text | Streaming | 32 | 3 | 0 | 16384 |
| Tool call | Nonstreaming | 128 | 27 | 0 | 16384 |
| Tool-result replay | Streaming | 32 | 2 | 0 | 16384 |

There are exactly three completion requests, one fresh30-second empty-state
gate, no retries and an empty postflight. No full CLI task speed is measured by
these probes. Native CLI integration and live backend behavior are qualified
separately; the real CLI loops were exercised with synthetic responses.

Final verification passes710 regression tests with six expected opt-in skips,
30 focused lifecycle/provider tests and eight native offline cells across old
v0.2 and new v0.3:124 OS checks and40 synthetic completions. Both new-condition
CLIs read/edit/search, run public tests, create and execute scratch files, retain
protected/hidden/controller denials and finish. Sleeping-child checks prove
cleanup and refusal to restart consumed attempts. Native v0.3 tool qualification
uses the existing JavaScript fixture. No new task is added. Scratch commands
use explicit files; unsupported Bash here-docs are stated in the prompt.

All411 earlier frozen source fingerprints and all frozen artifacts of the four
old Mirror/Vibe runs remain unchanged. All22 historical v0.2 request shapes,
including nonstreaming/uncapped context summaries, translate offline under the
new limits. Default v0.1 and the old contracts remain unchanged.

A matched four-system experiment still needs a separately versioned Pi
bridge/sandbox integration. These checks do not establish that Mirror now
finishes the old coding task within900 seconds or explain its earlier runtime
causally. The current item returns for owner feedback before expanding tasks
or integrating another harness.
