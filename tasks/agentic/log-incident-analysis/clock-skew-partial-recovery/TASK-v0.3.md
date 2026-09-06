# Incident analysis task v0.3

Investigate the production incident represented by the files under `logs/`.
Read only the files you need, correlate events across services and return one
structured incident report. Normalize report timestamps to UTC.

Do not assume that every host clock is correct. Use independent clock
observations, receive times and trace IDs to reconstruct causal order.
Distinguish root cause, exposing event, intermittent routing, downstream impact,
partial mitigation and full recovery.

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
- [AFFECTED-SCOPE] Report the primary failing service and the user journey that
  actually experienced the observed impact.
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
- [DISTRACTOR-REJECTION] Reject the plausible provider and database alternatives.
  Within each rejected-hypothesis entry, attach direct counter-evidence for that
  specific alternative; evidence attached elsewhere is insufficient.
- [BOUNDED-IMPACT] Include every supported authorization, latency and remaining-
  backlog code and exclude unsupported payment-loss or all-node outage claims.
- [REMEDIATION] Include immediate isolation, time synchronization, admission
  protection, clock-offset detection and backlog reconciliation actions.
- [UNCERTAINTY] Use the controlled uncertainty codes for material facts the
  supplied evidence does not establish.
- [UNSUPPORTED-CLAIMS] Do not claim provider or database causation, all-node
  skew, full recovery, payment loss, exact failure count, known change owner or
  known backlog completion unless supplied evidence establishes it.

A causal-chain item contains only `event_id` and `file`. An evidence item adds
its `supports` role. Return the final report through the harness's instructed
output mechanism.
