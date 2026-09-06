# Complete a typed payment-result API migration

The payment gateway used by `CheckoutService` no longer returns a boolean. It
now returns a typed `PaymentResult` with four distinct states. The current
migration handles success and retryable failures partially, but it treats all
other outcomes as retryable declines and ignores payment state already stored
for the order.

Change `CheckoutService` and `RetryPolicy` so that all of these requirements
hold:

1. Preserve the public constructors and method signatures of both classes.
   Modify no other source files.
2. Before contacting the gateway, read the order's current `PaymentState`. A
   state of `Paid`, `Declined` or `Pending` returns the matching
   `CheckoutOutcome` without a gateway call or repository write. Only `Unpaid`
   orders may be charged.
3. Every charge for an unpaid order uses the idempotency key
   `checkout:<order-id>`. Reuse that same key for every retry in the checkout
   invocation.
4. Retry only `PaymentStatus::RetryableFailure`, and only while the current
   one-based attempt number is below the policy's configured maximum. Never
   retry `Succeeded`, `Declined` or `Unknown`. Preserve validation requiring
   both the maximum and the supplied attempt number to be at least one.
5. On `Succeeded`, record exactly one paid transition with the provider
   reference and return `CheckoutOutcome::Paid`.
6. On `Declined`, do not retry. Record exactly one declined transition with the
   result reason and return `CheckoutOutcome::Declined`.
7. On `Unknown`, do not retry because a timeout or ambiguous transport result
   may already have charged the customer. Record exactly one pending transition
   with the result reason and return `CheckoutOutcome::Pending`.
8. If retryable failures exhaust the configured attempt limit, record exactly
   one pending transition with the final result's reason and return
   `CheckoutOutcome::Pending`.
9. Do not add dependencies or alter tests, Composer metadata, enums, value
   objects or interfaces.

Only `src/CheckoutService.php` and `src/RetryPolicy.php` may be changed.
