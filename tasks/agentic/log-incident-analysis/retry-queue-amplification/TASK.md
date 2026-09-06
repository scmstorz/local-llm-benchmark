# Incident analysis task

Investigate the production incident represented by the files under `logs/`.
Read only the files you need, correlate events across services and return one
structured incident report. Normalize report timestamps to UTC.

Distinguish the root cause from the condition that exposed it, amplification
mechanisms, user-visible effects and unrelated errors. A deployment can precede
the first symptom; do not assume that the loudest error is causal. Cite exact
event IDs and source files. Do not invent aggregate counts, ownership or data
loss. State material uncertainties explicitly.

Use these controlled codes where applicable:

- root cause: `retry_policy_regression`, `dependency_outage`,
  `message_broker_failure`, `notification_tls_failure`, `unknown`;
- trigger: `dependency_slowdown`, `traffic_increase`, `scheduled_job`,
  `credential_expiry`, `unknown`;
- rejected hypothesis: `message_broker_outage`,
  `notification_tls_failure`, `database_outage`;
- impact: `order_fulfillment_delayed`, `order_status_delayed`,
  `orders_lost`, `checkout_unavailable`, `notification_delivery_failed`;
- recommendation: `restore_bounded_backoff`, `cap_retry_amplification`,
  `alert_on_redelivery_ratio`, `load_test_degraded_dependency`,
  `replace_message_broker`, `rotate_notification_certificate`;
- uncertainty: `exact_delayed_order_count_unknown`,
  `retry_policy_change_owner_unknown`, `downstream_slowdown_origin_unknown`,
  `full_recovery_time_unknown`.

Set `recovery_status` to `full`, `partial` or `not_observed`. The
`last_observed_utc` field is the timestamp of the final evidence used to assess
recovery; it is not automatically proof of full recovery.

The final report must follow report contract v2 supplied by the harness. A
causal-chain item contains only `event_id` and `file`. An evidence item adds one
of `root_cause`, `trigger`, `symptom`, `impact`, `recovery` or
`rejected_hypothesis` as its `supports` value.
