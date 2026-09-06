# Incident analysis task v0.4

Investigate the production incident represented by the files under `logs/`.
Read only the files you need, correlate events across services and return one
structured incident report. Normalize report timestamps to UTC.

Distinguish the latent root cause from the condition that exposed it, the
amplification mechanism, user-visible effects and unrelated errors. A deployment
can precede the first user-visible impact; the loudest error need not be causal.

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
- [AFFECTED-SCOPE] Report the primary failing service and the user journey that
  actually experienced the observed delay. These two fields are descriptive
  labels, not controlled codes. Case, separators, `and` and repeated
  words do not change an otherwise identical service or journey label.
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
  alternatives. Within each rejected-hypothesis entry, attach direct
  counter-evidence for that specific alternative; evidence attached elsewhere
  is insufficient. One sufficient direct evidence group is enough; you do not
  need to attach every event that could support the rejection.
- [BOUNDED-IMPACT] Include every supported fulfillment and status-delay code and
  exclude unsupported order-loss, checkout-outage or production-notification
  claims.
- [REMEDIATION] Include bounded-backoff restoration, amplification control,
  detection and degraded-dependency testing supported by the mechanism.
- [UNCERTAINTY] Use the controlled uncertainty codes for material facts the
  supplied evidence does not establish.
- [UNSUPPORTED-CLAIMS] Do not claim broker causation, notification-TLS causation,
  unavailable inventory, lost orders, unavailable checkout, failed production
  notifications, exact delayed-order count, known owner or known slowdown origin
  unless supplied evidence establishes it.

A causal-chain item contains only `event_id` and `file`. An evidence item adds
its `supports` role. Return the final report through the harness's instructed
output mechanism.
