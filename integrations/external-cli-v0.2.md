# Mirror and Mistral Vibe normal-budget development checks v0.2

This condition follows the two excluded 120-second checks in
[v0.1](external-cli-v0.1.md). Both systems receive an explicit disposable workspace
path in the task prompt. Mirror's per-request completion ceiling is 8,192 tokens
instead of 3,000; its declared client context remains 16,384. Vibe's native
Python legacy loop still has no supported explicit output-token field. Package
versions, dependencies, native tools and containment are unchanged.

The separate [contract](../tasks/coding/track-b/external-cli-v0.2.json) preserves
v0.1 and is selected with `prepare --condition v0.2`. The default remains v0.1.
The parent budget is 900 seconds; the existing 300-second provider socket
timeout and remaining-parent-deadline bound remain in force. No total-token or
turn ceiling is added. The gateway records actual transmitted settings without
rewriting them. A larger output ceiling permits longer answers; it does not
guarantee completion or eliminate all provider/context limits.

The owner authorized exactly one new Qwen JavaScript attempt per harness after
these changes. Both use the unchanged `coding.dev.async-cache-coalescing`
fixture and verifier, separate fresh 30-second idle gates, no controller retry,
and an empty postflight. Other consumers may not be stopped. There is no empty
prompt preload: each attempt starts from the admitted empty model state.

Before inference, source inputs are committed, native synthetic read/edit/search,
public-test and denied-access checks pass for both updated conditions, and
sleeping-child deadline probes verify cleanup. A private one-shot plan binds
the exact source commit, run manifests, deployment digest, runtime version and
driver. Original v0.1 evidence is preserved without rewriting or rerunning it.

Report final public and hidden verification, runtime outcome, completion requests,
available token usage and native tool activity. If a successful source edit is
observed, bound its timing by the preceding provider response's completion and
the following request's arrival, and check the final source bytes independently.
This is an interval for a native edit, not an exact first-byte timestamp. Missing
final-response usage remains unknown rather than zero.

These are two descriptive development checks, excluded from the measured core
registry. Wall time, the explicit prompt and Mirror's output ceiling differ from
the initial checks, so any improvement cannot be attributed to time alone.
There are no repetitions or randomization and no general harness ranking.

## Observed closeout

The [completed checks](../reports/coding/external-cli-normal-budget-v0.2.md)
produce passing artifacts for both systems; only Vibe completes the overall
run within the parent budget. Native context management may lower Mirror's
configured main-loop output ceiling, and its summary request omits that field.
Neither native `none`/`off` declaration proves effective backend thinking
control: both observed streams contain reasoning text.

First confirmed edits are reported from native successful tool-result records,
checked against final source bytes. The planned adjacent-provider bracket can
overlap slightly because the client and recorder run concurrently; no exact
first-byte time is inferred. Original receipts remain tied to the pre-inference
source commit. A later recorder-only interrupted-stream correction is tested
offline without repeating either model run.
