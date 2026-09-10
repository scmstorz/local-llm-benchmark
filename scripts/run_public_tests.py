#!/usr/bin/env python3
"""Run the dependency-free tests supported by a sanitized public snapshot."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))


PUBLIC_TEST_MODULES = (
    "tests.test_agentic",
    "tests.test_challenger",
    "tests.test_checks",
    "tests.test_cli",
    "tests.test_coding",
    "tests.test_coding_track_a_report",
    "tests.test_log_incident",
    "tests.test_log_incident_checkout_v02",
    "tests.test_log_incident_mini",
    "tests.test_log_incident_mini_qualification",
    "tests.test_log_incident_mini_smoke_plan",
    "tests.test_log_incident_mini_v02",
    "tests.test_log_incident_mini_v03",
    "tests.test_log_incident_mini_v04",
    "tests.test_log_incident_mini_v05",
    "tests.test_log_incident_pi_qualification",
    "tests.test_log_incident_smokes",
    "tests.test_log_incident_sweep_quality_audit_v05",
    "tests.test_log_incident_v02",
    "tests.test_log_incident_v02_harness_qualifications",
    "tests.test_log_incident_v02_qualification",
    "tests.test_log_incident_v02_smoke_plans",
    "tests.test_log_incident_v02_smoke_report",
    "tests.test_log_incident_v03",
    "tests.test_log_incident_v03_qualification",
    "tests.test_log_incident_v04",
    "tests.test_log_incident_v04_qualification",
    "tests.test_log_incident_v05",
    "tests.test_log_incident_v05_qualification",
    "tests.test_mini_v03_adapter",
    "tests.test_mini_v03_qualification",
    "tests.test_mini_v03_report",
    "tests.test_mini_v03_smoke_plan",
    "tests.test_mini_v03_smoke_report",
    "tests.test_mini_v03_sweep",
    "tests.test_mini_v03_sweep_plan",
    "tests.test_model_catalog",
    "tests.test_model_lifecycle",
    "tests.test_ollama",
    "tests.test_opencode_qualification_card",
    "tests.test_pi_report",
    "tests.test_pi_v03_config",
    "tests.test_pi_v03_qualification",
    "tests.test_pi_v03_report",
    "tests.test_performance_reliability",
    "tests.test_json_schema",
    "tests.test_quality_evaluation_v02",
    "tests.test_quality_stochasticity",
    "tests.test_public_snapshot",
    "tests.test_report",
    "tests.test_suite_resume",
    "tests.test_track_b_replication_report",
    "tests.test_track_b_system_report",
)


def main() -> int:
    suite = unittest.defaultTestLoader.loadTestsFromNames(PUBLIC_TEST_MODULES)
    result = unittest.TextTestRunner(verbosity=1).run(suite)
    return 0 if result.wasSuccessful() else 1


if __name__ == "__main__":
    raise SystemExit(main())
