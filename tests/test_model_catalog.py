import json
import tempfile
import unittest
from pathlib import Path

from local_llm_benchmark.model_catalog import (
    ModelRegistrationConfig,
    register_models,
)


class FakeOllamaClient:
    def __init__(self, models: list[dict], version: str = "0.12.3") -> None:
        self.models = models
        self.ollama_version = version

    def version(self) -> dict:
        return {"version": self.ollama_version}

    def list_models(self) -> dict:
        return {"models": self.models}


class ModelCatalogTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.repo_root = Path(__file__).resolve().parents[1]

    def test_registration_is_idempotent_and_does_not_infer(self) -> None:
        client = FakeOllamaClient(
            [
                {
                    "name": "model-a:latest",
                    "digest": "a" * 64,
                    "size": 123,
                    "details": {"quantization_level": "Q4_K_M"},
                    "capabilities": ["tools", "completion", "tools"],
                }
            ]
        )
        with tempfile.TemporaryDirectory() as temporary_directory:
            repo_root = Path(temporary_directory)
            config = ModelRegistrationConfig(models=("model-a:latest",))

            first = register_models(repo_root, config, client=client)
            second = register_models(repo_root, config, client=client)
            catalog = json.loads(
                (repo_root / "models/catalog.json").read_text(encoding="utf-8")
            )

        self.assertEqual(first["added_count"], 1)
        self.assertEqual(second["added_count"], 0)
        self.assertTrue(first["no_inference_performed"])
        self.assertEqual(len(catalog["deployments"]), 1)
        deployment = catalog["deployments"][0]
        self.assertEqual(deployment["digest"], "a" * 64)
        self.assertEqual(deployment["capabilities"], ["completion", "tools"])
        self.assertEqual(deployment["qualification"]["track_a_text"], "eligible")
        self.assertTrue(deployment["qualification"]["native_tools_advertised"])
        self.assertEqual(deployment["qualification"]["track_b_opencode"], "unqualified")
        self.assertEqual(deployment["catalog_status"], "registered")

    def test_new_digest_or_runtime_appends_a_deployment(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            repo_root = Path(temporary_directory)
            config = ModelRegistrationConfig(models=("model-a:latest",))
            register_models(
                repo_root,
                config,
                client=FakeOllamaClient(
                    [{"name": "model-a:latest", "digest": "a" * 64}]
                ),
            )
            register_models(
                repo_root,
                config,
                client=FakeOllamaClient(
                    [{"name": "model-a:latest", "digest": "b" * 64}]
                ),
            )
            register_models(
                repo_root,
                config,
                client=FakeOllamaClient(
                    [{"name": "model-a:latest", "digest": "b" * 64}],
                    version="0.13.0",
                ),
            )
            catalog = json.loads(
                (repo_root / "models/catalog.json").read_text(encoding="utf-8")
            )

        self.assertEqual(len(catalog["deployments"]), 3)
        self.assertEqual(
            [item["digest"] for item in catalog["deployments"]],
            ["a" * 64, "b" * 64, "b" * 64],
        )
        self.assertEqual(
            len({item["deployment_id"] for item in catalog["deployments"]}), 3
        )

    def test_tracked_catalog_and_newcomer_cohort_are_consistent(self) -> None:
        catalog_path = self.repo_root / "models/catalog.json"
        cohort_path = (
            self.repo_root
            / "models/cohorts/capability-suite-2026-09-02.json"
        )
        catalog = json.loads(catalog_path.read_text(encoding="utf-8"))
        cohort = json.loads(cohort_path.read_text(encoding="utf-8"))
        deployments = {
            item["deployment_id"]: item for item in catalog["deployments"]
        }

        self.assertEqual(len(deployments), 16)
        self.assertEqual(
            sum(
                item["runtime"]["version"] == "0.32.15"
                for item in deployments.values()
            ),
            8,
        )
        self.assertEqual(
            sum(
                item["runtime"]["version"] == "0.33.2"
                for item in deployments.values()
            ),
            8,
        )
        self.assertEqual(cohort["status"], "complete")
        self.assertEqual(cohort["suite"]["case_count"], 15)
        self.assertEqual(cohort["suite"]["total_planned_requests"], 90)
        self.assertEqual(cohort["evaluation"]["scalar_candidate_count"], 107)
        self.assertEqual(cohort["evaluation"]["required_pairwise_count"], 83)
        for planned in cohort["execution_order"]:
            cataloged = deployments[planned["deployment_id"]]
            self.assertEqual(planned["requested_name"], cataloged["requested_name"])
            self.assertEqual(planned["digest"], cataloged["digest"])
            self.assertEqual(cataloged["qualification"]["track_a_text"], "eligible")
            self.assertEqual(planned["status"], "complete")
            self.assertEqual(planned["complete_cases"], 15)
            self.assertEqual(planned["runtime_failures"], 0)
            self.assertTrue(planned["sweep_id"].startswith("sweep-"))

        serialized = catalog_path.read_text(encoding="utf-8")
        self.assertNotIn("/Users/", serialized)


if __name__ == "__main__":
    unittest.main()
