import unittest
from pathlib import Path

from local_llm_benchmark.cli import build_parser


class CliContractTest(unittest.TestCase):
    def test_model_register_accepts_multiple_exact_names(self) -> None:
        args = build_parser().parse_args(
            ["model-register", "--models", "model:a", "model:b"]
        )

        self.assertEqual(args.command, "model-register")
        self.assertEqual(args.models, ["model:a", "model:b"])
        self.assertEqual(args.catalog, Path("models/catalog.json"))

    def test_challenger_bundles_accepts_repeated_sweep_directories(self) -> None:
        args = build_parser().parse_args(
            [
                "challenger-bundles",
                "--sweep-dir",
                "results/sweeps/a",
                "--sweep-dir",
                "results/sweeps/b",
            ]
        )

        self.assertEqual(
            args.sweep_dir,
            [Path("results/sweeps/a"), Path("results/sweeps/b")],
        )

    def test_suite_resume_selects_one_existing_sweep(self) -> None:
        args = build_parser().parse_args(
            ["suite-resume", "--sweep-dir", "results/sweeps/interrupted"]
        )

        self.assertEqual(args.command, "suite-resume")
        self.assertEqual(args.sweep_dir, Path("results/sweeps/interrupted"))

    def test_pi_sweep_and_resume_have_explicit_artifact_roots(self) -> None:
        start = build_parser().parse_args(["coding-agent-pi-sweep"])
        resume = build_parser().parse_args(
            [
                "coding-agent-pi-sweep-resume",
                "--sweep-dir",
                "results/agentic-sweeps/interrupted",
            ]
        )

        self.assertEqual(
            start.plan,
            Path("tasks/coding/track-b/pi-capability-sweep-v0.1.json"),
        )
        self.assertEqual(start.results_dir, Path("results/agentic-sweeps"))
        self.assertEqual(start.agent_results_dir, Path("results/agentic-runs"))
        self.assertEqual(
            resume.sweep_dir, Path("results/agentic-sweeps/interrupted")
        )


if __name__ == "__main__":
    unittest.main()
