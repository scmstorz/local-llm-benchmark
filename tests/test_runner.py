import hashlib
import json
import re
import tempfile
import unittest
from collections import Counter
from pathlib import Path

from local_llm_benchmark.challenger import (
    challenger_baseline_evidence,
    challenger_completion_result,
    summarize_candidate_counts,
)
from local_llm_benchmark.runner import (
    ComparisonConfig,
    RunnerError,
    comparison_run_config,
    comparison_completion_result,
    compact_run_result,
    create_judge_bundle,
    find_model,
    load_case,
    load_suite_manifest,
    nanoseconds_to_seconds,
    run_completion_result,
    suite_completion_result,
    tokens_per_second,
    validate_context_window,
)


class RunnerTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.repo_root = Path(__file__).resolve().parents[1]

    def test_load_case_verifies_private_source(self) -> None:
        loaded = load_case(
            self.repo_root,
            Path("tasks/summarization/dev/mit-sloan-ai-climate/case.json"),
        )
        self.assertEqual(
            loaded["case"]["case_id"],
            "summarization.dev.mit-sloan-ai-climate",
        )
        self.assertNotIn("{{SOURCE_TEXT}}", loaded["user_message"])
        self.assertIn("[K01]", loaded["user_message"])

    def test_load_research_paper_case_verifies_private_source(self) -> None:
        cases = (
            (
                "tasks/summarization/dev/the-agent-company/case.json",
                "summarization.dev.the-agent-company",
                "[P31]",
            ),
            (
                "tasks/summarization/dev/metr-long-software-tasks/case.json",
                "summarization.dev.metr-long-software-tasks",
                "[P19]",
            ),
        )
        for path, case_id, final_location in cases:
            with self.subTest(case_id=case_id):
                loaded = load_case(self.repo_root, Path(path))
                self.assertEqual(loaded["case"]["case_id"], case_id)
                self.assertNotIn("{{SOURCE_TEXT}}", loaded["user_message"])
                self.assertIn(final_location, loaded["user_message"])

    def test_general_knowledge_reference_is_hidden_from_candidate(self) -> None:
        loaded = load_case(
            self.repo_root,
            Path("tasks/general-knowledge/dev/confidence-intervals/case.json"),
        )

        self.assertEqual(
            loaded["case"]["prompt"]["source_delivery"],
            "judge_only",
        )
        self.assertIn("[S01]", loaded["source_path"].read_text(encoding="utf-8"))
        self.assertNotIn("[S01]", loaded["user_message"])
        self.assertNotIn("NIST", loaded["user_message"])

    def test_load_case_composes_multiple_candidate_artifacts(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            repo_root = Path(temporary_directory)
            (repo_root / "tasks/case/prompt").mkdir(parents=True)
            (repo_root / "inputs").mkdir()
            source_packet = repo_root / "inputs/source-packet.md"
            personal_thoughts = repo_root / "inputs/personal-thoughts.md"
            source_packet.write_text("[S01] Evidence.\n", encoding="utf-8")
            personal_thoughts.write_text("[T01] A personal thought.\n", encoding="utf-8")
            (repo_root / "tasks/case/prompt/system.txt").write_text(
                "System message.\n", encoding="utf-8"
            )
            (repo_root / "tasks/case/prompt/user.md").write_text(
                "Sources\n{{SOURCE_PACKET}}\nThoughts\n{{PERSONAL_THOUGHTS}}\n",
                encoding="utf-8",
            )
            for artifact_name in (
                "benchmark-card.json",
                "judge-instructions.md",
                "judge-result.schema.json",
            ):
                (repo_root / f"tasks/case/{artifact_name}").write_text(
                    "{}\n", encoding="utf-8"
                )

            def digest(path: Path) -> str:
                return hashlib.sha256(path.read_bytes()).hexdigest()

            metadata = {
                "source_id": "source-packet.test",
                "artifacts": {
                    "source_packet": {"sha256": digest(source_packet)},
                    "personal_thoughts": {"sha256": digest(personal_thoughts)},
                },
            }
            (repo_root / "tasks/case/source-metadata.json").write_text(
                json.dumps(metadata), encoding="utf-8"
            )
            case = {
                "case_id": "source_grounded_writing.dev.test",
                "case_version": "1.0.0",
                "input": {
                    "source_id": "source-packet.test",
                    "source_metadata_path": "tasks/case/source-metadata.json",
                    "candidate_artifacts": [
                        {
                            "id": "source_packet",
                            "path": "inputs/source-packet.md",
                            "metadata_artifact_key": "source_packet",
                            "placeholder": "{{SOURCE_PACKET}}",
                            "judge_bundle_name": "source-packet.md",
                        },
                        {
                            "id": "personal_thoughts",
                            "path": "inputs/personal-thoughts.md",
                            "metadata_artifact_key": "personal_thoughts",
                            "placeholder": "{{PERSONAL_THOUGHTS}}",
                            "judge_bundle_name": "personal-thoughts.md",
                        },
                    ],
                },
                "prompt": {
                    "system_path": "tasks/case/prompt/system.txt",
                    "user_template_path": "tasks/case/prompt/user.md",
                    "source_delivery": "candidate",
                },
                "evaluation": {
                    "benchmark_card_path": "tasks/case/benchmark-card.json",
                    "benchmark_card_version": "1.0.0",
                    "judge_instructions_path": "tasks/case/judge-instructions.md",
                    "judge_instructions_version": "1.0.0",
                    "judge_result_schema_path": "tasks/case/judge-result.schema.json",
                },
            }
            (repo_root / "tasks/case/case.json").write_text(
                json.dumps(case), encoding="utf-8"
            )

            loaded = load_case(repo_root, Path("tasks/case/case.json"))

            self.assertIn("[S01] Evidence.", loaded["user_message"])
            self.assertIn("[T01] A personal thought.", loaded["user_message"])
            self.assertNotIn("{{SOURCE_PACKET}}", loaded["user_message"])
            self.assertNotIn("{{PERSONAL_THOUGHTS}}", loaded["user_message"])
            self.assertEqual(
                [artifact["id"] for artifact in loaded["input_artifacts"]],
                ["source_packet", "personal_thoughts"],
            )

            run_dir = repo_root / "results/run-test"
            run_dir.mkdir(parents=True)
            bundle = create_judge_bundle(
                repo_root=repo_root,
                run_dir=run_dir,
                loaded_case=loaded,
                candidate_id="candidate-test",
                response_text="A response.",
                checks={"all_passed": True},
            )
            self.assertEqual(
                (bundle / "source/source-packet.md").read_text(encoding="utf-8"),
                "[S01] Evidence.\n",
            )
            self.assertEqual(
                (bundle / "source/personal-thoughts.md").read_text(encoding="utf-8"),
                "[T01] A personal thought.\n",
            )

    def test_all_source_grounded_writing_cases_are_consistent(self) -> None:
        base = self.repo_root / "tasks/source-grounded-writing/dev"
        for case_path in sorted(base.glob("*/case.json")):
            with self.subTest(case_path=case_path):
                case_dir = case_path.parent
                case = json.loads(case_path.read_text(encoding="utf-8"))
                metadata = json.loads(
                    (case_dir / "source-metadata.json").read_text(encoding="utf-8")
                )
                card = json.loads(
                    (case_dir / "benchmark-card.json").read_text(encoding="utf-8")
                )
                schema = json.loads(
                    (case_dir / "judge-result.schema.json").read_text(encoding="utf-8")
                )
                source_packet = (
                    self.repo_root
                    / case["input"]["candidate_artifacts"][0]["path"]
                )
                personal_thoughts = (
                    self.repo_root
                    / case["input"]["candidate_artifacts"][1]["path"]
                )
                source_text = source_packet.read_text(encoding="utf-8")
                thought_text = personal_thoughts.read_text(encoding="utf-8")

                self.assertEqual(
                    hashlib.sha256(source_packet.read_bytes()).hexdigest(),
                    metadata["artifacts"]["source_packet"]["sha256"],
                )
                self.assertEqual(
                    hashlib.sha256(personal_thoughts.read_bytes()).hexdigest(),
                    metadata["artifacts"]["personal_thoughts"]["sha256"],
                )
                self.assertEqual(len(metadata["sources"]), 5)
                self.assertEqual(
                    len(source_text.split()),
                    metadata["artifacts"]["source_packet"]["word_count_whitespace"],
                )
                self.assertEqual(
                    len(thought_text.split()),
                    metadata["artifacts"]["personal_thoughts"]["word_count_whitespace"],
                )
                for location_number in range(1, 26):
                    label = f"S{location_number:02d}"
                    self.assertEqual(
                        len(re.findall(rf"(?m)^\[{label}\]", source_text)), 1
                    )
                for thought_number in range(1, 4):
                    label = f"T{thought_number:02d}"
                    self.assertEqual(
                        len(re.findall(rf"(?m)^\[{label}\]", thought_text)), 1
                    )
                self.assertEqual(len(card["evidence_requirements"]), 10)
                self.assertEqual(
                    sum(item["weight"] for item in card["evidence_requirements"]),
                    25,
                )
                for requirement in card["evidence_requirements"]:
                    for source_location in requirement["source_locations"]:
                        self.assertIn(f"[{source_location}]", source_text)
                self.assertEqual(
                    card["score_construction"]["personal_thought_integration"]["items"],
                    ["T01", "T02", "T03"],
                )
                self.assertEqual(
                    sum(
                        dimension["max"]
                        for dimension in card["score_construction"]["judged_dimensions"]
                    ),
                    60,
                )
                self.assertEqual(card["score_construction"]["maximum"], 100)
                self.assertEqual(
                    case["evaluation"]["judge_result_schema_version"],
                    schema["properties"]["schema_version"]["const"],
                )
                self.assertEqual(case["case_id"], card["case_id"])
                self.assertEqual(
                    case["case_id"],
                    schema["properties"]["case"]["properties"]["case_id"]["const"],
                )

                loaded = load_case(self.repo_root, case_path)
                self.assertEqual(
                    [artifact["id"] for artifact in loaded["input_artifacts"]],
                    ["source_packet", "personal_thoughts"],
                )
                self.assertNotIn("{{SOURCE_PACKET}}", loaded["user_message"])
                self.assertNotIn("{{PERSONAL_THOUGHTS}}", loaded["user_message"])

    def test_source_grounded_writing_comparison_plans_are_frozen_and_consistent(
        self,
    ) -> None:
        base = self.repo_root / "tasks/source-grounded-writing/dev"
        plans = sorted(base.glob("*/comparison-plan.json"))
        self.assertEqual(len(plans), 2)

        for plan_path in plans:
            with self.subTest(plan_path=plan_path):
                plan = json.loads(plan_path.read_text(encoding="utf-8"))
                case_path = self.repo_root / plan["case_path"]
                case = json.loads(case_path.read_text(encoding="utf-8"))
                card = json.loads(
                    (case_path.parent / "benchmark-card.json").read_text(
                        encoding="utf-8"
                    )
                )

                self.assertEqual(plan["status"], "frozen_before_execution")
                self.assertEqual(plan["case_id"], case["case_id"])
                self.assertEqual(set(plan["models"]), set("ABCDE"))
                self.assertEqual(set(plan["execution_order"]), set("ABCDE"))
                self.assertEqual(len(plan["execution_order"]), 5)
                self.assertEqual(
                    len({model["name"] for model in plan["models"].values()}),
                    5,
                )
                for model in plan["models"].values():
                    self.assertRegex(model["digest"], r"^[0-9a-f]{64}$")
                self.assertEqual(
                    plan["methodology"]["num_ctx"],
                    case["input"]["minimum_num_ctx"],
                )
                self.assertEqual(
                    plan["evaluation"]["quality_scale_maximum"],
                    card["score_construction"]["maximum"],
                )

    def test_all_general_knowledge_cases_are_blinded_and_consistent(self) -> None:
        base = self.repo_root / "tasks/general-knowledge/dev"
        schema = json.loads(
            (self.repo_root / "tasks/general-knowledge/judge-result.schema.json").read_text(
                encoding="utf-8"
            )
        )
        for case_path in sorted(base.glob("*/case.json")):
            with self.subTest(case_path=case_path):
                loaded = load_case(self.repo_root, case_path)
                case = loaded["case"]
                card = json.loads(
                    (case_path.parent / "benchmark-card.json").read_text(encoding="utf-8")
                )
                source = loaded["source_path"].read_text(encoding="utf-8")

                self.assertEqual(case["prompt"]["source_delivery"], "judge_only")
                self.assertFalse(case["input"]["reference_visible_to_candidate"])
                self.assertFalse(case["input"]["candidate_browsing_allowed"])
                self.assertFalse(case["input"]["candidate_tools_allowed"])
                self.assertNotIn("[S01]", loaded["user_message"])
                self.assertEqual(case["case_id"], card["case_id"])
                self.assertEqual(case["case_version"], card["case_version"])
                self.assertEqual(
                    case["evaluation"]["judge_result_schema_version"],
                    schema["properties"]["schema_version"]["const"],
                )
                self.assertEqual(len(card["key_facts"]), 8)
                self.assertEqual(len(card["key_ideas"]), 4)
                self.assertEqual(sum(item["weight"] for item in card["key_facts"]), 25)
                self.assertEqual(sum(item["weight"] for item in card["key_ideas"]), 15)
                for item in card["key_facts"] + card["key_ideas"]:
                    for location in item["source_locations"]:
                        self.assertIn(f"[{location}]", source)

    def test_transfer_case_exposes_scenario_but_hides_judge_analysis(self) -> None:
        loaded = load_case(
            self.repo_root,
            Path(
                "tasks/general-knowledge/dev/confidence-intervals-transfer/case.json"
            ),
        )

        self.assertIn("10.000 freiwillige Plattformnutzer", loaded["user_message"])
        self.assertIn("[-0,10; +1,70]", loaded["user_message"])
        self.assertIn("+0,50-Punkte-Schwelle", loaded["user_message"])
        self.assertNotIn("American Statistical Association", loaded["user_message"])
        self.assertNotIn("Gelman", loaded["user_message"])

    def test_hard_knowledge_v02_is_frozen_complete_and_position_balanced(self) -> None:
        manifest_path = (
            self.repo_root / "tasks/general-knowledge/hard-knowledge-v0.2.json"
        )
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        schedule = manifest["execution_schedule"]
        aliases = set(manifest["models"])

        self.assertEqual(manifest["status"], "frozen_before_execution")
        self.assertTrue(
            manifest["selection_policy"][
                "selection_completed_before_any_suite_run"
            ]
        )
        self.assertEqual(len(schedule), 6)
        self.assertEqual(
            [entry["position"] for entry in schedule],
            list(range(1, 7)),
        )
        self.assertEqual(
            manifest["fixed_inference"],
            {
                "ollama_endpoint": "http://127.0.0.1:11434",
                "temperature": 0.0,
                "seed": 42,
                "think": False,
                "num_ctx": 8192,
                "num_predict": 2600,
                "keep_alive": "10m",
                "timeout_seconds": 600.0,
            },
        )

        case_ids = set()
        position_counts = {alias: Counter() for alias in aliases}
        for entry in schedule:
            with self.subTest(case_id=entry["case_id"]):
                self.assertEqual(set(entry["model_order"]), aliases)
                case_path = self.repo_root / entry["case_path"]
                loaded = load_case(self.repo_root, case_path)
                self.assertEqual(loaded["case"]["case_id"], entry["case_id"])
                self.assertEqual(loaded["case"]["difficulty"], "hard")
                self.assertNotIn(entry["case_id"], case_ids)
                case_ids.add(entry["case_id"])
                for position, alias in enumerate(entry["model_order"], start=1):
                    position_counts[alias][position] += 1

        for alias, counts in position_counts.items():
            with self.subTest(alias=alias):
                values = [counts[position] for position in range(1, 5)]
                self.assertEqual(sum(values), 6)
                self.assertLessEqual(max(values) - min(values), 1)

    def test_case_minimum_context_is_enforced(self) -> None:
        case = {
            "case_id": "summarization.dev.example",
            "input": {"minimum_num_ctx": 16384},
        }
        with self.assertRaisesRegex(RunnerError, "requires --num-ctx 16384"):
            validate_context_window(case, 8192)
        validate_context_window(case, 16384)

    def test_capability_suite_covers_every_text_development_case(self) -> None:
        loaded = load_suite_manifest(
            self.repo_root,
            Path("tasks/capability-suite-v0.3.json"),
        )
        entries = loaded["cases"]
        declared_paths = {item["entry"]["case_path"] for item in entries}
        actual_paths = {
            str(path.relative_to(self.repo_root))
            for path in self.repo_root.glob("tasks/*/dev/*/case.json")
            if "coding" not in path.parts
        }

        self.assertEqual(len(entries), 15)
        self.assertEqual(declared_paths, actual_paths)
        self.assertEqual(
            sum(item["entry"]["canonical_baseline_available"] for item in entries),
            11,
        )

        previous = load_suite_manifest(
            self.repo_root,
            Path("tasks/capability-suite-v0.2.json"),
        )
        self.assertEqual(len(previous["cases"]), 14)
        self.assertEqual(previous["manifest"]["suite_version"], "0.2.0")

        legacy = load_suite_manifest(
            self.repo_root,
            Path("tasks/capability-suite-v0.1.json"),
        )
        self.assertEqual(len(legacy["cases"]), 13)
        self.assertEqual(legacy["manifest"]["suite_version"], "0.1.0")

    def test_suite_completion_result_withholds_private_mapping(self) -> None:
        result = suite_completion_result(
            {
                "sweep_id": "sweep-test",
                "status": "complete",
                "case_count": 2,
                "complete_case_count": 2,
                "failed_case_count": 0,
                "quality_candidate_count": 2,
                "deployment": {"model": "model:secret"},
            },
            Path("results/sweeps/sweep-test"),
        )

        serialized = json.dumps(result)
        self.assertNotIn("model:secret", serialized)
        self.assertNotIn("candidate-secret", serialized)
        self.assertEqual(result["quality_candidate_count"], 2)

    def test_challenger_completion_result_withholds_private_mapping(self) -> None:
        result = challenger_completion_result(
            {
                "batch_id": "challenger-test",
                "status": "ready_for_blinded_judgment",
                "case_count": 11,
                "candidate_count_per_case": 5,
                "minimum_candidate_count": 5,
                "maximum_candidate_count": 5,
                "judge_bundles": "judge-bundles/",
                "private_mapping": {"candidate-secret": "model:secret"},
            },
            Path("results/challenger-evaluations/challenger-test"),
        )

        serialized = json.dumps(result)
        self.assertNotIn("candidate-secret", serialized)
        self.assertNotIn("model:secret", serialized)
        self.assertEqual(result["case_count"], 11)

    def test_challenger_late_baseline_requires_explicit_opt_in(self) -> None:
        sweep_case = {
            "case_id": "general_knowledge.dev.late-baseline",
            "canonical_baseline_available": False,
        }

        with self.assertRaisesRegex(RunnerError, "not marked baseline-compatible"):
            challenger_baseline_evidence(
                sweep_case,
                allow_late_baseline=False,
            )
        self.assertEqual(
            challenger_baseline_evidence(
                sweep_case,
                allow_late_baseline=True,
                challenger_completed_at="2026-08-29T10:00:00Z",
                comparison_completed_at="2026-08-29T11:00:00Z",
            ),
            "completed_after_challenger_sweep",
        )
        with self.assertRaisesRegex(RunnerError, "pass --allow-late-baseline"):
            challenger_baseline_evidence(
                sweep_case,
                allow_late_baseline=False,
                challenger_completed_at="2026-08-29T10:00:00Z",
                comparison_completed_at="2026-08-29T11:00:00Z",
            )
        self.assertEqual(
            challenger_baseline_evidence(
                sweep_case,
                allow_late_baseline=False,
                challenger_completed_at="2026-08-29T10:00:00Z",
                comparison_completed_at="2026-08-29T09:00:00Z",
            ),
            "completed_before_challenger_run",
        )
        self.assertEqual(
            challenger_baseline_evidence(
                {"canonical_baseline_available": True},
                allow_late_baseline=False,
            ),
            "available_at_challenger_sweep",
        )

    def test_challenger_candidate_count_summary_handles_mixed_baselines(self) -> None:
        self.assertEqual(
            summarize_candidate_counts([7, 7]),
            {
                "candidate_count_per_case": 7,
                "minimum_candidate_count": 7,
                "maximum_candidate_count": 7,
            },
        )
        self.assertEqual(
            summarize_candidate_counts([7, 8]),
            {
                "candidate_count_per_case": None,
                "minimum_candidate_count": 7,
                "maximum_candidate_count": 8,
            },
        )

    def test_find_model_uses_exact_name_and_preserves_digest(self) -> None:
        record = find_model(
            {
                "models": [
                    {
                        "name": "qwen3:4b",
                        "digest": "abc123",
                    }
                ]
            },
            "qwen3:4b",
        )
        self.assertEqual(record["digest"], "abc123")

    def test_metric_conversions(self) -> None:
        self.assertEqual(nanoseconds_to_seconds(2_000_000_000), 2.0)
        self.assertEqual(tokens_per_second(20, 2_000_000_000), 10.0)
        self.assertIsNone(tokens_per_second(20, 0))

    def test_comparison_run_config_preserves_settings_and_adds_phase(self) -> None:
        comparison = ComparisonConfig(
            models=("model:a", "model:b"),
            temperature=0.2,
            keep_alive="15m",
        )
        run = comparison_run_config(
            comparison,
            model="model:a",
            comparison_id="comparison-test",
            phase="warm",
        )
        self.assertEqual(run.model, "model:a")
        self.assertEqual(run.temperature, 0.2)
        self.assertEqual(run.keep_alive, "15m")
        self.assertEqual(run.comparison_id, "comparison-test")
        self.assertEqual(run.measurement_phase, "warm")
        self.assertEqual(run.measurement_iteration, 1)

    def test_compact_comparison_result_omits_candidate_id(self) -> None:
        compact = compact_run_result(
            {
                "run_id": "run-test",
                "candidate_id": "candidate-secret",
                "measurement_phase": "warm",
                "measurement_iteration": 1,
                "status": "complete",
                "done_reason": "stop",
                "checks": {"generation_complete": True},
                "metrics": {"wall_time_seconds": 1.25},
            }
        )

        self.assertNotIn("candidate_id", compact)
        self.assertEqual(compact["run_id"], "run-test")
        self.assertEqual(compact["measurement_phase"], "warm")

    def test_comparison_completion_result_withholds_model_mapping(self) -> None:
        result = comparison_completion_result(
            comparison_dir=Path("results/comparisons/comparison-test"),
            record={
                "comparison_id": "comparison-test",
                "status": "complete",
                "models": [
                    {"model": "model:secret-a"},
                    {"model": "model:secret-b"},
                ],
            },
            quality_candidate_count=2,
        )

        serialized = json.dumps(result)
        self.assertNotIn("model:secret", serialized)
        self.assertNotIn("candidate-secret", serialized)
        self.assertEqual(result["model_count"], 2)
        self.assertEqual(result["quality_candidate_count"], 2)

    def test_single_completion_result_withholds_model_mapping(self) -> None:
        result = run_completion_result(
            {
                "run_id": "run-test",
                "run_dir": "results/runs/run-test",
                "candidate_id": "candidate-secret",
                "model": "model:secret",
                "status": "complete",
                "done_reason": "stop",
                "checks": {"generation_complete": True},
                "metrics": {"wall_time_seconds": 1.25},
            }
        )

        serialized = json.dumps(result)
        self.assertNotIn("candidate-secret", serialized)
        self.assertNotIn("model:secret", serialized)
        self.assertEqual(result["run_id"], "run-test")

    def test_case_card_and_judge_versions_are_consistent(self) -> None:
        base = self.repo_root / "tasks/summarization/dev/mit-sloan-ai-climate"
        case = json.loads((base / "case.json").read_text(encoding="utf-8"))
        card = json.loads((base / "benchmark-card.json").read_text(encoding="utf-8"))
        schema = json.loads((base / "judge-result.schema.json").read_text(encoding="utf-8"))

        schema_case = schema["properties"]["case"]["properties"]
        schema_judge = schema["properties"]["judge"]["properties"]
        self.assertEqual(case["case_version"], card["case_version"])
        self.assertEqual(case["case_version"], schema_case["case_version"]["const"])
        self.assertEqual(
            case["evaluation"]["benchmark_card_version"],
            card["card_version"],
        )
        self.assertEqual(card["card_version"], schema_case["card_version"]["const"])
        self.assertEqual(
            case["evaluation"]["judge_result_schema_version"],
            schema["properties"]["schema_version"]["const"],
        )
        self.assertEqual(
            case["evaluation"]["judge_instructions_version"],
            schema_judge["instructions_version"]["const"],
        )

    def test_research_paper_card_and_judge_versions_are_consistent(self) -> None:
        case_directories = (
            "tasks/summarization/dev/the-agent-company",
            "tasks/summarization/dev/metr-long-software-tasks",
        )
        for case_directory in case_directories:
            with self.subTest(case_directory=case_directory):
                base = self.repo_root / case_directory
                case = json.loads((base / "case.json").read_text(encoding="utf-8"))
                card = json.loads(
                    (base / "benchmark-card.json").read_text(encoding="utf-8")
                )
                schema = json.loads(
                    (base / "judge-result.schema.json").read_text(encoding="utf-8")
                )

                schema_case = schema["properties"]["case"]["properties"]
                schema_judge = schema["properties"]["judge"]["properties"]
                self.assertEqual(case["case_version"], card["case_version"])
                self.assertEqual(
                    case["case_version"], schema_case["case_version"]["const"]
                )
                self.assertEqual(
                    case["evaluation"]["benchmark_card_version"],
                    card["card_version"],
                )
                self.assertEqual(
                    card["card_version"], schema_case["card_version"]["const"]
                )
                self.assertEqual(
                    case["evaluation"]["judge_result_schema_version"],
                    schema["properties"]["schema_version"]["const"],
                )
                self.assertEqual(
                    case["evaluation"]["judge_instructions_version"],
                    schema_judge["instructions_version"]["const"],
                )

    def test_research_paper_card_weights_and_locations_are_valid(self) -> None:
        cases = (
            (
                "tasks/summarization/dev/the-agent-company",
                "data/private/summarization/dev/the-agent-company/source.md",
            ),
            (
                "tasks/summarization/dev/metr-long-software-tasks",
                "data/private/summarization/dev/metr-long-software-tasks/source.md",
            ),
        )
        for case_directory, source_path in cases:
            with self.subTest(case_directory=case_directory):
                base = self.repo_root / case_directory
                card = json.loads(
                    (base / "benchmark-card.json").read_text(encoding="utf-8")
                )
                source = (self.repo_root / source_path).read_text(encoding="utf-8")

                self.assertEqual(len(card["key_facts"]), 10)
                self.assertEqual(len(card["key_ideas"]), 5)
                self.assertEqual(
                    sum(item["weight"] for item in card["key_facts"]), 25
                )
                self.assertEqual(
                    sum(item["weight"] for item in card["key_ideas"]), 15
                )
                for item in card["key_facts"] + card["key_ideas"]:
                    for source_location in item["source_locations"]:
                        self.assertIn(f"[{source_location}]", source)

    def test_judge_bundle_contains_no_model_identity(self) -> None:
        loaded = load_case(
            self.repo_root,
            Path("tasks/summarization/dev/mit-sloan-ai-climate/case.json"),
        )
        checks = {
            "check_version": "1.0.0",
            "nonempty": True,
            "detected_language": "de",
            "language_method": "stopword_heuristic_v1",
            "language_evidence": {
                "german_stopword_hits": 5,
                "english_stopword_hits": 0,
            },
            "language_pass": True,
            "word_count": 5,
            "maximum_words": 1000,
            "maximum_words_pass": True,
            "source_location_labels_absent": True,
            "markdown_heading_count": 1,
            "bold_heading_count": 0,
            "structural_heading_count": 1,
            "heading_pass": True,
            "reasoning_markup_absent": True,
            "generation_done_reason": "stop",
            "generation_complete": True,
        }
        with tempfile.TemporaryDirectory() as temporary_directory:
            run_dir = Path(temporary_directory) / "run-test"
            run_dir.mkdir()
            bundle = create_judge_bundle(
                repo_root=self.repo_root,
                run_dir=run_dir,
                loaded_case=loaded,
                candidate_id="candidate-abcdef",
                response_text="# Ergebnis\n\nEine deutsche Zusammenfassung.",
                checks=checks,
            )
            manifest = json.loads((bundle / "manifest.json").read_text(encoding="utf-8"))
            self.assertTrue(manifest["anonymized"])
            self.assertFalse(manifest["model_identity_included"])
            self.assertEqual(manifest["candidate_ids"], ["candidate-abcdef"])
            for path in bundle.rglob("*"):
                if path.is_file():
                    self.assertNotIn("qwen3:4b", path.read_text(encoding="utf-8"))

    def test_general_knowledge_bundle_contains_judge_reference(self) -> None:
        loaded = load_case(
            self.repo_root,
            Path("tasks/general-knowledge/dev/confidence-intervals/case.json"),
        )
        with tempfile.TemporaryDirectory() as temporary_directory:
            run_dir = Path(temporary_directory) / "run-test"
            run_dir.mkdir()
            bundle = create_judge_bundle(
                repo_root=self.repo_root,
                run_dir=run_dir,
                loaded_case=loaded,
                candidate_id="candidate-abcdef",
                response_text="# Erklärung\n\nEine deutsche Antwort.",
                checks={},
            )

            reference_copy = (bundle / "source/source.md").read_text(encoding="utf-8")
            candidate_copy = (bundle / "candidates/candidate-abcdef.md").read_text(
                encoding="utf-8"
            )
            self.assertIn("[S01]", reference_copy)
            self.assertNotIn("[S01]", candidate_copy)
            self.assertTrue((bundle / "tasks/general-knowledge/judge-instructions.md").exists())


if __name__ == "__main__":
    unittest.main()
