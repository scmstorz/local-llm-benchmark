# PHP payment-result migration

Case ID: `coding.dev.php-payment-result-migration`

This is the third Track A coding case and the first PHP case. It asks a model
to finish migrating a small checkout service from success-versus-failure logic
to a typed four-state payment result while preserving idempotency and avoiding
duplicate or unsafe side effects.

## Why this case

The first two coding cases covered a localized Python pagination bug and a
single-module JavaScript asynchronous cache feature. This case adds a work-
relevant but framework-neutral PHP 8.4 service boundary:

- two collaborating writable classes rather than one focal function;
- an `api_migration` task family;
- enums, readonly value objects and typed interfaces;
- business-state short-circuiting;
- retry classification and attempt limits;
- stable payment idempotency keys;
- distinct success, decline, unknown and exhausted-retry persistence.

The fixture deliberately avoids Composer installation and framework behavior.
This keeps Track A focused on model capability under fixed context. A future
Track B case can add a real framework, tools, dependency resolution and test
feedback as separate system variables.

## Track A contract

The candidate sees all fourteen fixture files but may replace only
`src/CheckoutService.php` and `src/RetryPolicy.php`. It receives no tools,
hidden tests or test feedback. Its response must contain one or two strict
whole-file envelopes. Interfaces, enums, value objects, tests and Composer
metadata are protected.

The verifier records `php --version`, runs four candidate-visible checks and
then eight candidate-hidden checks from outside the disposable fixture. No
package installation or network access is required.

## Current validation state

The intentionally partial baseline passes 2/4 public and 3/8 hidden checks. It
retries declines and unknown outcomes, ignores final repository state and maps
exhausted retryable or ambiguous results to a decline. The independent
reference implementation passes all twelve checks.

One explicitly authorized excluded Ornith development smoke is complete. The
model emitted two plausible PHP files inside ordinary Markdown code fences
instead of the required path-bearing whole-file envelopes. The controller did
not infer paths or repair the response, so no candidate artifact was installed
and no PHP test executed. The frozen outcome is `verified_success=false` with
`failure_code=malformed_artifact`. This smoke is not a comparison result or a
reliability estimate.

A separately authorized post-hoc diagnostic removed only the Markdown fence
lines, mapped the two unique class names to the two allowed paths and added the
required envelope markers. SHA-256 checks prove that neither PHP file changed.
Under this normalized transport, the exact candidate code passed all 4 public
and 8 hidden checks. This verifies the code semantics under the current test
suite but does not change the original malformed outcome. See the tracked
[`diagnostic report`](../../../../reports/coding/php-payment-result-migration-ornith-smoke-diagnostic.md).

The separately frozen five-model comparison is also complete in `BCEDA` order.
Its immutable primary result is 0/5 strict verified successes: four visible
responses violated the exact transport grammar, and GPT-OSS emitted no visible
candidate. The preregistered secondary protocol verified Ornith's exact code at
12/12. Clearly post-hoc, code-byte-identical audits additionally found 12/12
solutions from Qwen 3.8 and Muse Glimmer; Qwen 3.6 remained a code failure with
a PHP parse error. See the formal and diagnostic layers in the
[`comparison report`](../../../../reports/coding/php-payment-result-migration-track-a-v1.md).
