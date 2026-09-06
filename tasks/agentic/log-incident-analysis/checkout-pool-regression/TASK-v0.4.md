# Incident analysis task v0.4

Investigate the production incident represented by the files under `logs/`.
Read only the files you need, correlate events across services and return one
structured incident report. Normalize report timestamps to UTC.

Distinguish the root cause from contributing triggers, downstream symptoms and
unrelated warnings. Do not invent request counts, deployment ownership or other
facts absent from the logs.

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
- [AFFECTED-SCOPE] Report the primary failing service and the user journey that
  actually experienced the observed impact. These two fields are descriptive
  labels, not controlled codes. Case, separators, `and` and repeated
  words do not change an otherwise identical service or journey label.
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
  alternatives. Within each rejected-hypothesis entry, attach the direct
  counter-evidence for that specific alternative; citing the evidence elsewhere
  or under another hypothesis is insufficient. One sufficient direct evidence
  group is enough; you do not need to attach every event that could support the
  rejection.
- [BOUNDED-IMPACT] Include every supported checkout impact code and exclude
  unsupported login, database-availability or data-loss escalation.
- [REMEDIATION] Include immediate restoration, preventive configuration
  validation and early-detection actions supported by the incident mechanism.
- [UNCERTAINTY] Use the controlled uncertainty codes for material facts the
  supplied evidence does not establish.
- [UNSUPPORTED-CLAIMS] Do not claim a database or authentication cause, data
  loss, login outage, unavailable database, exact affected-request count, known
  owner or exact recovery end unless supplied evidence establishes it.

A causal-chain item contains only `event_id` and `file`. An evidence item adds
its `supports` role. Return the final report through the harness's instructed
output mechanism.
