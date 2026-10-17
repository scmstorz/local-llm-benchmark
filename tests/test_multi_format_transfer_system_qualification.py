from __future__ import annotations

import hashlib
import unittest
from pathlib import Path

from local_llm_benchmark.runner import load_json


REPO_ROOT = Path(__file__).resolve().parents[1]
CASE_PATH = REPO_ROOT / (
    "tasks/agentic/multi-format-document-analysis/"
    "supplier-award-reconciliation/case-v0.2.json"
)
OFFLINE_PATH = CASE_PATH.with_name("offline-qualification-v0.2.json")


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


class MultiFormatTransferSystemQualificationTests(unittest.TestCase):
    def test_case_names_two_qualified_complete_systems(self) -> None:
        case = load_json(CASE_PATH)
        harness = case["track_b_harness"]
        self.assertEqual(case["status"], "complete_systems_qualified_pending_smoke_freeze")
        self.assertEqual(harness["complete_system_adaptation_status"], "qualified")
        self.assertEqual(
            [item["harness_id"] for item in harness["systems"]],
            ["mini-multi-format-v0.2", "pi-multi-format-v0.4"],
        )
        for item in harness["systems"]:
            self.assertTrue((REPO_ROOT / item["harness_path"]).is_file())
            self.assertTrue((REPO_ROOT / item["qualification_path"]).is_file())

    def test_each_system_qualification_binds_every_artifact(self) -> None:
        case = load_json(CASE_PATH)
        for system in case["track_b_harness"]["systems"]:
            qualification = load_json(REPO_ROOT / system["qualification_path"])
            with self.subTest(harness_id=system["harness_id"]):
                self.assertEqual(qualification["harness_id"], system["harness_id"])
                self.assertEqual(qualification["live_ollama_requests"], 0)
                self.assertFalse(qualification["live_model_inference"])
                for item in qualification["artifacts"]:
                    path = REPO_ROOT / item["path"]
                    self.assertEqual(item["sha256"], digest(path))

    def test_systems_share_backend_and_functional_actions_but_not_identity(self) -> None:
        combined_path = REPO_ROOT / (
            "tasks/agentic/track-b/"
            "multi-format-transfer-complete-systems-v0.2-qualification.json"
        )
        combined = load_json(combined_path)
        shared = combined["shared_boundary"]
        self.assertEqual(
            shared["artifact_backend_sha256"],
            digest(REPO_ROOT / shared["artifact_backend_path"]),
        )
        self.assertEqual(
            shared["artifact_operations"],
            ["list_artifacts", "read_docx", "read_pdf", "read_xlsx"],
        )
        self.assertEqual(shared["completion_operation"], "finish_report")
        self.assertTrue(shared["functional_action_surface_equal"])
        self.assertFalse(combined["system_specific_boundary"]["same_system_claim"])
        for item in combined["bound_artifacts"]:
            self.assertEqual(item["sha256"], digest(REPO_ROOT / item["path"]))

    def test_pi_v04_binds_real_thirteen_check_acceptance_and_strict_capture(self) -> None:
        qualification = load_json(
            REPO_ROOT / "tasks/agentic/track-b/pi-multi-format-v0.4-qualification.json"
        )
        evidence = qualification["qualification_evidence"]
        self.assertEqual(evidence["fresh_real_seatbelt_checks_passed"], 13)
        self.assertEqual(evidence["fresh_real_seatbelt_checks_total"], 13)
        self.assertTrue(evidence["structured_report_capture_exact"])
        self.assertTrue(evidence["surrounding_free_text_without_finish_report_rejected"])
        self.assertTrue(evidence["private_ipv6_loopback_probe_allowed"])
        self.assertFalse(qualification["correction"]["free_text_fallback_admitted"])
        self.assertFalse(qualification["correction"]["post_hoc_surrounding_text_normalization"])

    def test_offline_record_binds_all_complete_system_qualifications(self) -> None:
        qualification = load_json(OFFLINE_PATH)
        self.assertEqual(
            qualification["status"],
            "complete_systems_qualified_pending_smoke_freeze",
        )
        systems = qualification["complete_systems"]
        for prefix in ("protocol", "mini_qualification", "pi_qualification", "combined_qualification"):
            path = REPO_ROOT / systems[f"{prefix}_path"]
            self.assertEqual(systems[f"{prefix}_sha256"], digest(path))
        self.assertEqual(
            qualification["blocking_gates"],
            [
                "design and freeze a separate excluded no-retry transfer smoke",
                "obtain a separate post-freeze authorization before any Ollama request",
            ],
        )


if __name__ == "__main__":
    unittest.main()
