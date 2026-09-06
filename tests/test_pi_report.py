import unittest

from local_llm_benchmark.pi_report import diagnose_pi_outcome


def diagnose(
    *,
    raw: dict | None = None,
    trajectory: dict | None = None,
    verification: dict | None = None,
    audit: list[dict] | None = None,
    provider_error: str | None = None,
) -> dict:
    return diagnose_pi_outcome(
        raw_outcome=raw or {},
        trajectory=trajectory or {},
        verification=verification or {},
        audit_events=audit or [],
        provider_error=provider_error,
        active_wall_limit=900,
    )


class PiReportTests(unittest.TestCase):
    def test_verified_success_is_conclusive(self) -> None:
        result = diagnose(raw={"verified_success": True})

        self.assertEqual(result["evidence_status"], "conclusive_success")

    def test_output_budget_is_a_conclusive_bounded_failure(self) -> None:
        result = diagnose(audit=[{"kind": "output_token_budget_exceeded"}])

        self.assertEqual(result["type"], "maximum_total_output_tokens_exceeded")
        self.assertEqual(result["evidence_status"], "conclusive_bounded_failure")

    def test_standby_wall_clock_abort_is_inconclusive(self) -> None:
        result = diagnose(
            trajectory={"active_wall_time_seconds": 31.9},
            audit=[{"kind": "agent_budget_exceeded"}],
        )

        self.assertEqual(result["type"], "policy_wall_clock_included_standby")
        self.assertEqual(result["evidence_status"], "inconclusive_negative")

    def test_provider_timeout_is_inconclusive(self) -> None:
        result = diagnose(provider_error="provider_request_timeout")

        self.assertEqual(result["category"], "provider_or_transport_failure")
        self.assertEqual(result["evidence_status"], "inconclusive_negative")

    def test_clean_verifier_failure_is_conclusive(self) -> None:
        result = diagnose(
            raw={"agent_termination_valid": True},
            verification={
                "verified_success": False,
                "failure_code": "hidden_tests_failed",
            },
        )

        self.assertEqual(result["type"], "hidden_tests_failed")
        self.assertEqual(result["evidence_status"], "conclusive_task_failure")


if __name__ == "__main__":
    unittest.main()
