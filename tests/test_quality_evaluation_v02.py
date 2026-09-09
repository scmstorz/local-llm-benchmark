import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from local_llm_benchmark.quality_evaluation_v02 import (
    evaluation_status,
    freeze_pairwise_results,
    freeze_scalar_results,
    initialize_evaluation,
    reveal_and_aggregate,
)
from local_llm_benchmark.runner import RunnerError, load_json, sha256_file


def write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")


class QualityEvaluationV02Tests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.repo = Path(self.temporary.name)
        self.study = self.repo / "study"
        self.bundle = self.study / "judge-bundles" / "C"
        self.results = self.repo / "judge-inputs"
        self.results.mkdir(parents=True)
        self.candidates = ["candidate-a1", "candidate-b1", "candidate-a2", "candidate-b2"]
        self._create_bundle()
        self._create_private_records()
        self._create_scalar_inputs()
        self.pair_input = self.repo / "pairwise.json"
        self._write_pair_input()

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def _schema(self) -> dict:
        return {
            "type": "object",
            "additionalProperties": False,
            "required": [
                "schema_version",
                "evaluation_id",
                "case",
                "candidate_id",
                "deterministic_checks",
                "errors",
                "score_summary",
                "verdict",
            ],
            "properties": {
                "schema_version": {"const": "test-1"},
                "evaluation_id": {"type": "string", "minLength": 1},
                "case": {
                    "type": "object",
                    "additionalProperties": False,
                    "required": ["case_id"],
                    "properties": {"case_id": {"const": "case.test"}},
                },
                "candidate_id": {"type": "string", "pattern": "^candidate-[a-z0-9]+$"},
                "deterministic_checks": {"$ref": "#/$defs/checks"},
                "errors": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "additionalProperties": False,
                        "required": ["severity", "type"],
                        "properties": {
                            "severity": {"enum": ["critical", "major", "minor"]},
                            "type": {"enum": ["scope_inflation", "other"]},
                            "known_error_id": {"type": ["string", "null"]},
                        },
                    },
                },
                "score_summary": {
                    "type": "object",
                    "additionalProperties": False,
                    "required": ["final_total"],
                    "properties": {
                        "final_total": {"type": "number", "minimum": 0, "maximum": 100}
                    },
                },
                "verdict": {"enum": ["excellent", "good", "usable", "poor", "invalid"]},
            },
            "$defs": {
                "checks": {
                    "type": "object",
                    "additionalProperties": False,
                    "required": [
                        "nonempty",
                        "language_pass",
                        "maximum_words_pass",
                        "source_location_labels_absent",
                        "heading_pass",
                        "reasoning_markup_absent",
                        "generation_complete",
                    ],
                    "properties": {
                        key: {"type": "boolean"}
                        for key in (
                            "nonempty",
                            "language_pass",
                            "maximum_words_pass",
                            "source_location_labels_absent",
                            "heading_pass",
                            "reasoning_markup_absent",
                            "generation_complete",
                        )
                    },
                }
            },
        }

    def _checks(self) -> dict:
        return {
            "nonempty": True,
            "language_pass": True,
            "maximum_words_pass": True,
            "source_location_labels_absent": True,
            "heading_pass": True,
            "reasoning_markup_absent": True,
            "generation_complete": True,
        }

    def _create_bundle(self) -> None:
        schema_path = self.bundle / "tasks/case/judge-result.schema.json"
        write_json(schema_path, self._schema())
        artifacts = [
            {"path": "tasks/case/judge-result.schema.json", "sha256": sha256_file(schema_path)}
        ]
        content = {
            "candidate-a1": "same model-a output\n",
            "candidate-a2": "same model-a output\n",
            "candidate-b1": "first model-b output\n",
            "candidate-b2": "second model-b output\n",
        }
        for candidate_id in self.candidates:
            candidate_path = self.bundle / "candidates" / f"{candidate_id}.md"
            candidate_path.parent.mkdir(parents=True, exist_ok=True)
            candidate_path.write_text(content[candidate_id], encoding="utf-8")
            checks_path = self.bundle / "checks" / f"{candidate_id}.json"
            write_json(checks_path, self._checks())
            artifacts.extend(
                [
                    {
                        "path": f"candidates/{candidate_id}.md",
                        "sha256": sha256_file(candidate_path),
                    },
                    {
                        "path": f"checks/{candidate_id}.json",
                        "sha256": sha256_file(checks_path),
                    },
                ]
            )
        pair_plan = {
            "schema_version": "1.0.0",
            "case_id": "case.test",
            "pairs": [
                {
                    "pair_id": "pair-1",
                    "repetition": 1,
                    "candidate_a": "candidate-a1",
                    "candidate_b": "candidate-b1",
                },
                {
                    "pair_id": "pair-2",
                    "repetition": 2,
                    "candidate_a": "candidate-b2",
                    "candidate_b": "candidate-a2",
                },
            ],
        }
        pair_path = self.bundle / "pairwise-plan.json"
        write_json(pair_path, pair_plan)
        artifacts.append({"path": "pairwise-plan.json", "sha256": sha256_file(pair_path)})
        write_json(
            self.bundle / "manifest.json",
            {
                "schema_version": "1.0.0",
                "case_id": "case.test",
                "candidate_ids": self.candidates,
                "anonymized": True,
                "model_identity_included": False,
                "artifacts": artifacts,
            },
        )

    def _create_private_records(self) -> None:
        mapping = {}
        units = []
        for candidate_id in self.candidates:
            model_alias = candidate_id.removeprefix("candidate-")[0]
            repetition = int(candidate_id[-1])
            model = f"model-{model_alias}"
            unit_id = f"unit-{model_alias}{repetition}"
            run_id = f"run-{model_alias}{repetition}"
            mapping[candidate_id] = {
                "model": model,
                "digest": f"digest-{model_alias}",
                "case_id": "case.test",
                "repetition": repetition,
                "run_id": run_id,
                "unit_id": unit_id,
            }
            wall = 10 + (repetition * 2) if model_alias == "a" else 20 + (repetition * 4)
            units.append(
                {
                    "unit_id": unit_id,
                    "case_alias": "C",
                    "deployment_alias": model_alias.upper(),
                    "status": "complete",
                    "failure": None,
                    "run": {
                        "run_id": run_id,
                        "metrics": {
                            "wall_time_seconds": wall,
                            "time_to_first_content_seconds": wall / 2,
                            "eval_duration_seconds": wall / 3,
                            "output_tokens_per_second": 30 if model_alias == "a" else 15,
                        },
                    },
                }
            )
        write_json(
            self.study / "judge-bundles/private-map.json",
            {"schema_version": "1.0.0", "private_model_mapping": mapping},
        )
        plan = {
            "deployments": [
                {"alias": "A", "name": "model-a", "digest": "digest-a"},
                {"alias": "B", "name": "model-b", "digest": "digest-b"},
            ],
            "cases": [{"alias": "C", "case_id": "case.test"}],
        }
        plan_path = self.repo / "plan.json"
        write_json(plan_path, plan)
        write_json(
            self.study / "study.json",
            {
                "study_id": "study-test",
                "plan": {"path": "plan.json", "sha256": sha256_file(plan_path)},
                "units": units,
            },
        )

    def _create_scalar_inputs(self) -> None:
        for candidate_id in self.candidates:
            is_a = "-a" in candidate_id
            repetition = int(candidate_id[-1])
            errors = []
            if not is_a:
                errors = [
                    {
                        "severity": "critical",
                        "type": "scope_inflation",
                        "known_error_id": "KE01",
                    }
                ]
            score = (88 + repetition * 2) if is_a else 59
            write_json(
                self.results / f"{candidate_id}.json",
                {
                    "schema_version": "test-1",
                    "evaluation_id": f"evaluation-{candidate_id}",
                    "case": {"case_id": "case.test"},
                    "candidate_id": candidate_id,
                    "deterministic_checks": self._checks(),
                    "errors": errors,
                    "score_summary": {"final_total": score},
                    "verdict": "excellent" if is_a else "poor",
                },
            )

    def _write_pair_input(self) -> None:
        write_json(
            self.pair_input,
            {
                "schema_version": "quality_evaluation_pairwise_input_v0.2",
                "comparisons": [
                    {
                        "case_id": "case.test",
                        "pair_id": "pair-1",
                        "repetition": 1,
                        "candidate_a": "candidate-a1",
                        "candidate_b": "candidate-b1",
                        "preference": "A",
                        "rationale": "A is better grounded.",
                    },
                    {
                        "case_id": "case.test",
                        "pair_id": "pair-2",
                        "repetition": 2,
                        "candidate_a": "candidate-b2",
                        "candidate_b": "candidate-a2",
                        "preference": "B",
                        "rationale": "B is better grounded.",
                    },
                ],
            },
        )

    def test_pre_reveal_phases_do_not_read_private_mapping_or_study(self) -> None:
        from local_llm_benchmark import quality_evaluation_v02 as module

        real_load = module.load_json

        def guarded(path: Path) -> dict:
            if path.name in {"private-map.json", "study.json"}:
                raise AssertionError(f"private artifact read before reveal: {path}")
            return real_load(path)

        with patch.object(module, "load_json", side_effect=guarded):
            initialize_evaluation(self.study)
            freeze_scalar_results(self.study, self.results)
            freeze_pairwise_results(self.study, self.pair_input)
            status = evaluation_status(self.study)
        serialized = json.dumps(status)
        self.assertEqual(status["phase"], "pairwise_frozen")
        self.assertNotIn("model-a", serialized)
        self.assertNotIn("wall_time", serialized)

    def test_phase_order_is_irreversible(self) -> None:
        initialize_evaluation(self.study)
        with self.assertRaisesRegex(RunnerError, "Scalar results must be frozen"):
            freeze_pairwise_results(self.study, self.pair_input)
        with self.assertRaisesRegex(RunnerError, "Both scalar and pairwise"):
            reveal_and_aggregate(self.repo, self.study)
        freeze_scalar_results(self.study, self.results)
        with self.assertRaisesRegex(RunnerError, "Both scalar and pairwise"):
            reveal_and_aggregate(self.repo, self.study)

    def test_scalar_schema_coverage_and_frozen_checks_are_enforced(self) -> None:
        initialize_evaluation(self.study)
        target = self.results / "candidate-a1.json"
        invalid = load_json(target)
        invalid["unexpected"] = True
        write_json(target, invalid)
        with self.assertRaisesRegex(RunnerError, "Invalid judge result"):
            freeze_scalar_results(self.study, self.results)

        invalid.pop("unexpected")
        invalid["deterministic_checks"]["nonempty"] = False
        write_json(target, invalid)
        with self.assertRaisesRegex(RunnerError, "Deterministic checks changed"):
            freeze_scalar_results(self.study, self.results)

    def test_pairwise_plan_orientation_and_coverage_are_enforced(self) -> None:
        freeze_scalar_results(self.study, self.results)
        pairwise = load_json(self.pair_input)
        pairwise["comparisons"][0]["candidate_a"] = "candidate-b1"
        write_json(self.pair_input, pairwise)
        with self.assertRaisesRegex(RunnerError, "orientation"):
            freeze_pairwise_results(self.study, self.pair_input)

    def test_freeze_mutation_is_detected(self) -> None:
        freeze_scalar_results(self.study, self.results)
        path = self.study / "evaluation-v0.2/scalar-freeze.json"
        path.write_text(path.read_text(encoding="utf-8") + " ", encoding="utf-8")
        with self.assertRaisesRegex(RunnerError, "missing or changed"):
            evaluation_status(self.study)

    def test_reveal_generates_separate_public_outcome_layers(self) -> None:
        freeze_scalar_results(self.study, self.results)
        freeze_pairwise_results(self.study, self.pair_input)
        status = reveal_and_aggregate(self.repo, self.study)
        self.assertEqual(status["phase"], "revealed")
        aggregate = load_json(self.study / "evaluation-v0.2/aggregate-public.json")
        rows = {row["model"]: row for row in aggregate["results"]}
        self.assertEqual(rows["model-a"]["quality"]["scores_by_repetition"], [
            {"repetition": 1, "score": 90},
            {"repetition": 2, "score": 92},
        ])
        self.assertEqual(rows["model-a"]["pairwise"], {"wins": 2, "losses": 0, "ties": 0})
        self.assertEqual(rows["model-a"]["variation"]["unique_response_hashes"], 1)
        self.assertEqual(rows["model-a"]["variation"]["byte_identical_group_sizes"], [2])
        self.assertEqual(rows["model-b"]["errors"]["recurring_known_error_ids"], [
            {"value": "KE01", "count": 2}
        ])
        self.assertEqual(rows["model-b"]["reliability"]["technical_successes"], 2)
        self.assertEqual(rows["model-a"]["performance"]["wall_time_seconds"]["median_p50"], 13)
        percentile_fields = {
            key.lower()
            for row in aggregate["results"]
            for layer in (row["quality"]["score_distribution"], *row["performance"].values())
            if layer is not None
            for key in layer
        }
        self.assertTrue({"p90", "p95", "p99"}.isdisjoint(percentile_fields))
        self.assertNotIn("candidate-a1", json.dumps(aggregate))
        self.assertNotIn("run-a1", json.dumps(aggregate))
        report = (self.study / "evaluation-v0.2/report-public.md").read_text(encoding="utf-8")
        self.assertIn("model-a", report)
        self.assertIn("KE01 × 2", report)
        self.assertNotIn("candidate-a1", report)


if __name__ == "__main__":
    unittest.main()
