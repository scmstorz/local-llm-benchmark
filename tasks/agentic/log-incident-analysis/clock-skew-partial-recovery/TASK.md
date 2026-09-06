# Incident analysis task

Investigate the production incident represented by the files under `logs/`.
Read only the files you need, correlate events across services and return one
structured incident report. Normalize report timestamps to UTC.

Do not assume that every host clock is correct. Where timestamps conflict, use
independent clock observations, receive times and trace IDs to reconstruct the
causal order. Distinguish the root cause from the event that exposed it,
downstream symptoms, partial mitigation and full recovery. Cite exact event IDs
and source files. Do not invent request totals, full recovery, ownership or
data loss. State material uncertainties explicitly.

Use these controlled codes where applicable:

- root cause: `host_clock_skew`, `provider_outage`,
  `database_replication_failure`, `certificate_expiry`, `unknown`;
- trigger: `node_reentered_pool`, `traffic_increase`, `provider_rate_limit`,
  `database_failover`, `unknown`;
- rejected hypothesis: `payment_provider_outage`,
  `database_replication_failure`, `certificate_expiry`;
- impact: `checkout_authorization_failed`, `checkout_latency_increased`,
  `reconciliation_backlog_remaining`, `payments_lost`,
  `all_payment_nodes_unavailable`;
- recommendation: `remove_skewed_node`, `restore_time_synchronization`,
  `reject_unhealthy_clock_offset`, `alert_on_clock_offset`,
  `reconcile_pending_authorizations`, `replace_payment_provider`;
- uncertainty: `exact_failed_checkout_count_unknown`,
  `clock_configuration_change_owner_unknown`,
  `backlog_full_recovery_time_unknown`, `payment_data_loss_unknown`.

Set `recovery_status` to `full`, `partial` or `not_observed`. The
`last_observed_utc` field is the time of the last supplied recovery-state
evidence. It does not imply the incident was fully resolved.

The final report must follow report contract v2 supplied by the harness. A
causal-chain item contains only `event_id` and `file`. An evidence item adds one
of `root_cause`, `trigger`, `symptom`, `impact`, `recovery` or
`rejected_hypothesis` as its `supports` value.
