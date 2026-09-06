# Incident analysis task v0.5

Investigate the production incident represented by the files under `logs/`.
Read only the files you need, correlate events across services and return one
structured incident report. Normalize report timestamps to UTC.

Distinguish the root cause from contributing triggers, downstream symptoms and
unrelated warnings. Do not invent request counts, deployment ownership or other
facts absent from the logs.

Use exactly one of these controlled scope IDs in each corresponding report
field. Do not append component or host detail to these fields; put useful detail
in the summaries and evidence instead:

- `primary_service`: `payment-api`, `order-service`, `postgres-primary`,
  `authentication-service`;
- `affected_user_journey`: `checkout`, `login`, `order_status`.

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

## Visible verification contract

- [REPORT-SCHEMA] Follow report contract v2 exactly. Return every required field
  and no additional field.
- [INCIDENT-START] Set `start_utc` to the earliest timestamp in the supplied
  evidence that directly proves user-facing impact on the reported journey. A
  deployment, configuration change, traffic trigger or internal saturation
  event that occurs earlier is not the incident start unless that same evidence
  directly demonstrates user-facing impact.
- [LAST-OBSERVATION] Set `last_observed_utc` to the timestamp of the final
  supplied evidence used to assess recovery. It is not automatically proof of
  full recovery.
- [RECOVERY-STATUS] Set `recovery_status` to `full`, `partial` or
  `not_observed` according to that final supplied evidence.
- [AFFECTED-SCOPE] Select the primary failing service and affected journey from
  the visible controlled scope IDs above. Match the IDs exactly and put any
  component detail in prose or evidence instead of modifying the ID.
- [ROOT-CAUSE] Classify the underlying defect separately from traffic, symptoms,
  impact and recovery.
- [TRIGGER] Identify the event or condition that exposed the underlying defect.
- [CITATIONS] Use only exact supplied event IDs and their exact source files.
- [CAUSAL-CHAIN] Order the evidence-supported sequence from cause and trigger
  through propagation, user impact and recovery. Extra relevant events are
  allowed, but they must not invert that sequence.
- [EVIDENCE-ROLES] Associate critical evidence directly with one of
  `root_cause`, `trigger`, `symptom`, `impact`, `recovery` or
  `rejected_hypothesis`. Evidence for downstream propagation is a `symptom`;
  evidence that users received errors or latency is `impact`. Assign an event
  its most direct role; duplicating one event under multiple roles is not
  required.
- [DISTRACTOR-REJECTION] Reject the plausible database and authentication
  alternatives. Only event IDs listed in that entry's `evidence_ids` count as
  attached counter-evidence; an ID mentioned only in `reason`, another field or
  another hypothesis does not count. Every event used by the reason as proof
  must therefore also appear in that entry's `evidence_ids`. One sufficient
  direct evidence group is enough; exhaustive evidence is not required.
- [BOUNDED-IMPACT] Include every supported checkout impact code and exclude
  unsupported login, database-availability or data-loss escalation.
- [REMEDIATION] Include immediate restoration, preventive configuration
  validation and early-detection actions supported by the incident mechanism.
- [UNCERTAINTY] Use the controlled uncertainty codes for material facts the
  supplied evidence does not establish.
- [CONTROLLED-CODE-INTEGRITY] Use only values from the visible scope and code
  lists for machine-scored categorical fields. The deterministic verifier does
  not infer assertion versus negation from free-text substrings. Free-text
  summaries must still avoid unsupported database or authentication causation,
  data loss, login outage, unavailable database, exact affected-request counts,
  known ownership or an exact recovery end; those claims are reviewed in the
  separate human/LLM calibration layer.

A causal-chain item contains only `event_id` and `file`. An evidence item adds
its `supports` role. Return the final report through the harness's instructed
output mechanism.
