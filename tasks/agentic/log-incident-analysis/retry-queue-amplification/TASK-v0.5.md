# Incident analysis task v0.5

Investigate the production incident represented by the files under `logs/`.
Read only the files you need, correlate events across services and return one
structured incident report. Normalize report timestamps to UTC.

Distinguish the latent root cause from the condition that exposed it, the
amplification mechanism, user-visible effects and unrelated errors. A deployment
can precede the first user-visible impact; the loudest error need not be causal.

Use exactly one of these controlled scope IDs in each corresponding report
field. Do not append component or host detail to these fields; put useful detail
in the summaries and evidence instead:

- `primary_service`: `order-worker`, `inventory`, `message-broker`,
  `notification-service`, `order-api`;
- `affected_user_journey`: `order_status_and_fulfillment`, `checkout`,
  `notification_delivery`.

Use these controlled codes where applicable:

- root cause: `retry_policy_regression`, `dependency_outage`,
  `message_broker_failure`, `notification_tls_failure`, `unknown`;
- trigger: `dependency_slowdown`, `traffic_increase`, `scheduled_job`,
  `credential_expiry`, `unknown`;
- rejected hypothesis: `message_broker_outage`,
  `notification_tls_failure`, `database_outage`;
- impact: `order_fulfillment_delayed`, `order_status_delayed`, `orders_lost`,
  `checkout_unavailable`, `notification_delivery_failed`;
- recommendation: `restore_bounded_backoff`, `cap_retry_amplification`,
  `alert_on_redelivery_ratio`, `load_test_degraded_dependency`,
  `replace_message_broker`, `rotate_notification_certificate`;
- uncertainty: `exact_delayed_order_count_unknown`,
  `retry_policy_change_owner_unknown`, `downstream_slowdown_origin_unknown`,
  `full_recovery_time_unknown`.

## Visible verification contract

- [REPORT-SCHEMA] Follow report contract v2 exactly. Return every required field
  and no additional field.
- [INCIDENT-START] Set `start_utc` to the earliest timestamp in the supplied
  evidence that directly proves user-facing delay or incorrect status on the
  reported journey. The retry-policy deployment, dependency slowdown, immediate
  retry or queue growth is not the incident start unless that same evidence
  directly demonstrates user-facing impact.
- [LAST-OBSERVATION] Set `last_observed_utc` to the timestamp of the final
  supplied evidence used to assess recovery. It is not automatically proof of
  full recovery.
- [RECOVERY-STATUS] Set `recovery_status` to `full`, `partial` or
  `not_observed`. Full recovery requires evidence after both policy restoration
  and queue drain.
- [AFFECTED-SCOPE] Select the primary failing service and affected journey from
  the visible controlled scope IDs above. Match the IDs exactly and put any
  component detail in prose or evidence instead of modifying the ID.
- [ROOT-CAUSE] Classify the latent retry-policy defect separately from the
  dependency slowdown, queue amplification and user effects.
- [TRIGGER] Identify the event or condition that exposed the latent defect.
- [CITATIONS] Use only exact supplied event IDs and their exact source files.
- [CAUSAL-CHAIN] Order the evidence-supported sequence from latent cause and
  trigger through immediate retries, queue amplification, user impact and
  recovery. Extra relevant events may not invert that sequence.
- [EVIDENCE-ROLES] Associate critical evidence directly with one of
  `root_cause`, `trigger`, `symptom`, `impact`, `recovery` or
  `rejected_hypothesis`. Retry and queue-amplification observations are
  `symptom`; user-visible order delays are `impact`. Assign an event its most
  direct role; duplicating one event under multiple roles is not required.
- [DISTRACTOR-REJECTION] Reject the plausible broker-outage and notification-TLS
  alternatives. Only event IDs listed in that entry's `evidence_ids` count as
  attached counter-evidence; an ID mentioned only in `reason`, another field or
  another hypothesis does not count. Every event used by the reason as proof
  must therefore also appear in that entry's `evidence_ids`. One sufficient
  direct evidence group is enough; exhaustive evidence is not required.
- [BOUNDED-IMPACT] Include every supported fulfillment and status-delay code and
  exclude unsupported order-loss, checkout-outage or production-notification
  claims.
- [REMEDIATION] Include bounded-backoff restoration, amplification control,
  detection and degraded-dependency testing supported by the mechanism.
- [UNCERTAINTY] Use the controlled uncertainty codes for material facts the
  supplied evidence does not establish.
- [CONTROLLED-CODE-INTEGRITY] Use only values from the visible scope and code
  lists for machine-scored categorical fields. The deterministic verifier does
  not infer assertion versus negation from free-text substrings. Free-text
  summaries must still avoid unsupported broker or notification-TLS causation,
  unavailable inventory, lost orders, unavailable checkout, failed production
  notifications, exact delayed-order counts, known ownership or a known
  slowdown origin; those claims are reviewed in the separate human/LLM
  calibration layer.

A causal-chain item contains only `event_id` and `file`. An evidence item adds
its `supports` role. Return the final report through the harness's instructed
output mechanism.
