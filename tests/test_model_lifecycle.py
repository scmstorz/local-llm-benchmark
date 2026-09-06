import unittest
from pathlib import Path

from local_llm_benchmark.model_lifecycle import (
    default_sweep_models,
    load_model_lifecycle,
    models_with_status,
)


class ModelLifecycleTests(unittest.TestCase):
    def setUp(self) -> None:
        self.repo_root = Path.cwd().resolve()
        self.lifecycle = load_model_lifecycle(self.repo_root)

    def test_default_sweep_excludes_retired_and_opt_in_models(self) -> None:
        self.assertEqual(
            default_sweep_models(self.lifecycle),
            [
                "qwen3.6:35b-a3b-mxfp8",
                "qwen3.8:27b-mlx",
                "muse-glimmer:30b-mlx",
                "ornith-1.5:35b",
                "gemma4:31b-mlx",
            ],
        )

    def test_gpt_oss_is_retired_but_available_only_as_negative_control(self) -> None:
        retired = [
            entry
            for entry in self.lifecycle["models"]
            if entry["model"] == "gpt-oss:20b"
        ]

        self.assertEqual(len(retired), 1)
        self.assertEqual(retired[0]["status"], "retired_from_active_cohort")
        self.assertFalse(retired[0]["include_in_default_sweeps"])
        self.assertEqual(retired[0]["allowed_explicit_roles"], ["negative_control"])
        self.assertTrue(retired[0]["historical_results_retained"])

    def test_specialist_and_diagnostic_models_require_explicit_selection(self) -> None:
        self.assertEqual(
            models_with_status(
                self.lifecycle, {"specialist_opt_in", "diagnostic_only"}
            ),
            [
                "nemotron-3.5-lightning:30b-mlx",
                "granite4.2:30b",
            ],
        )


if __name__ == "__main__":
    unittest.main()
