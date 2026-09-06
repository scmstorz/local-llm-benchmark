# Incident analysis task v0.5

Investigate the production incident represented by the files under `logs/`.
Read only the files you need, correlate events across services and return one
structured incident report. Normalize report timestamps to UTC.

Do not assume that every host clock is correct. Use independent clock
observations, receive times and trace IDs to reconstruct causal order.
Distinguish root cause, exposing event, intermittent routing, downstream impact,
partial mitigation and full recovery.

Use exactly one of these controlled scope IDs in each corresponding report
field. Do not append component or host detail to these fields; put useful detail
in the summaries and evidence instead:

- `primary_service`: `payment-validation`, `payment-provider`,
  `database-replication`, `checkout-edge`;
- `affected_user_journey`: `checkout_authorization`, `payment_capture`,
  `reconciliation`.

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

## Visible verification contract

- [REPORT-SCHEMA] Follow report contract v2 exactly. Return every required field
  and no additional field.
- [INCIDENT-START] Set `start_utc` to the earliest reliable timestamp in the
  supplied evidence that directly proves user-facing checkout-authorization
  impact. Clock-skew detection, node admission or an internally logged rejection
  that occurs earlier is not the incident start unless that same evidence
  directly demonstrates user-facing impact. Correct skewed-host timestamps by
  using independent receive-time or offset evidence.
- [LAST-OBSERVATION] Set `last_observed_utc` to the reliable timestamp of the
  final supplied evidence used to assess recovery. It is not automatically proof
  of full recovery.
- [RECOVERY-STATUS] Set `recovery_status` to `full`, `partial` or
  `not_observed`. Restored new-request success is only partial while an evidenced
  reconciliation backlog remains.
- [AFFECTED-SCOPE] Select the primary failing service and affected journey from
  the visible controlled scope IDs above. Match the IDs exactly and put any
  component detail in prose or evidence instead of modifying the ID.
- [ROOT-CAUSE] Classify host clock skew separately from node admission,
  intermittent routing and downstream failures.
- [TRIGGER] Identify the event or condition that exposed the latent clock defect.
- [CITATIONS] Use only exact supplied event IDs and their exact source files.
- [CAUSAL-CHAIN] Order the evidence-supported sequence using corrected causal
  time: image/time defect, offset evidence, node admission, rejection,
  user-visible impact, isolation, new-request recovery and remaining backlog.
  Extra relevant events may not invert that sequence.
- [EVIDENCE-ROLES] Associate critical evidence directly with one of
  `root_cause`, `trigger`, `symptom`, `impact`, `recovery` or
  `rejected_hypothesis`. User errors and backlog creation are `impact`; isolation,
  restored new traffic and the final backlog state are `recovery` evidence.
  Assign an event its most direct role; duplicating one event under multiple
  roles is not required. A rejection emitted by the skewed node is a `symptom`,
  while the independent clock observation is `root_cause` evidence.
- [DISTRACTOR-REJECTION] Reject the plausible provider and database alternatives.
  Only event IDs listed in that entry's `evidence_ids` count as attached
  counter-evidence; an ID mentioned only in `reason`, another field or another
  hypothesis does not count. Every event used by the reason as proof must
  therefore also appear in that entry's `evidence_ids`. One sufficient direct
  evidence group is enough; exhaustive evidence is not required.
- [BOUNDED-IMPACT] Include every supported authorization, latency and remaining-
  backlog code and exclude unsupported payment-loss or all-node outage claims.
- [REMEDIATION] Include immediate isolation, time synchronization, admission
  protection, clock-offset detection and backlog reconciliation actions.
- [UNCERTAINTY] Use the controlled uncertainty codes for material facts the
  supplied evidence does not establish.
- [CONTROLLED-CODE-INTEGRITY] Use only values from the visible scope and code
  lists for machine-scored categorical fields. The deterministic verifier does
  not infer assertion versus negation from free-text substrings. Free-text
  summaries must still avoid unsupported provider or database causation,
  all-node skew, full recovery, payment loss, exact failure counts, known change
  ownership or known backlog completion; those claims are reviewed in the
  separate human/LLM calibration layer.

A causal-chain item contains only `event_id` and `file`. An evidence item adds
its `supports` role. Return the final report through the harness's instructed
output mechanism.
