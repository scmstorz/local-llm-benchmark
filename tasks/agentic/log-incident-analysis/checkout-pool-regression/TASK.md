# Incident analysis task

Investigate the production incident represented by the files under `logs/`.
Read only the files you need, correlate events across services and return one
structured incident report. All report timestamps must be normalized to UTC.

Distinguish the root cause from contributing triggers, downstream symptoms and
unrelated warnings. Cite exact event IDs and their source files. Do not invent
request counts, deployment ownership or other facts that are absent from the
logs. State material uncertainties explicitly.

Use these controlled codes where applicable:

- root cause: `configuration_regression`, `dependency_outage`,
  `authentication_failure`, `network_partition`, `capacity_exhaustion`,
  `unknown`;
- trigger: `traffic_increase`, `scheduled_job`, `dependency_slowdown`,
  `credential_expiry`, `unknown`;
- rejected hypothesis: `database_outage`, `authentication_failure`,
  `inventory_failure`, `network_partition`;
- impact: `checkout_requests_failed`, `checkout_latency_increased`,
  `login_outage`, `database_unavailable`, `data_loss`;
- recommendation: `restore_safe_pool_limit`, `validate_capacity_configuration`,
  `alert_on_pool_saturation`, `canary_load_test`, `rotate_credentials`,
  `increase_database_capacity`;
- uncertainty: `exact_affected_request_count_unknown`,
  `configuration_change_owner_unknown`, `recovery_end_time_unknown`.

The final report must follow the object shape supplied by the harness. A causal
chain item contains only `event_id` and `file`. An evidence item additionally
uses one of `root_cause`, `trigger`, `symptom`, `impact`, `recovery` or
`rejected_hypothesis` as its `supports` value.
