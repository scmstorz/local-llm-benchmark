import copy
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from local_llm_benchmark import practical_calibration as pc


BASE = "tasks/calibration/practical-profiles-v0.1"
CASE = BASE + "/document-decision/calibration-case.json"


class CalibrationMaterialsTests(unittest.TestCase):
    def test_real_materials_bind_sources_and_all_twenty_two_exact_calculations(self):
        result = pc.audit(pc.ROOT, str(pc.PLAN))
        self.assertEqual(sum(c["reference_calculations"] for c in result["cases"]), 22)
        self.assertEqual(result["proposed_generation_requests"], 20)
        self.assertEqual(result["model_requests_executed"], 0)
        self.assertFalse(result["inference_supported_by_this_module"])
        for c in result["cases"]:
            self.assertLess(c["input_utf8_bytes"], 20000)

    def test_candidate_messages_exclude_reference_rubric_and_instructions(self):
        data = pc.materials(pc.ROOT, CASE)
        self.assertEqual([m["role"] for m in data["messages"]], ["system", "user"])
        joined = "\n".join(m["content"] for m in data["messages"])
        self.assertIn("[D6]", joined)
        self.assertNotIn("expected_fraction", joined)
        self.assertNotIn("A-quality", joined)
        self.assertNotIn("Bewertungsablauf v1", joined)

    def test_reference_arithmetic_is_exact_and_does_not_execute_code(self):
        self.assertEqual(pc.expression("(11280/1250)/(9400/1000)*100-100", {}), -4)
        for expr in ["__import__('os').getcwd()", "2**100000", "data[0]", "True", "1.5"]:
            with self.subTest(expr=expr), self.assertRaises(ValueError):
                pc.expression(expr, {})

    def test_changed_reference_evidence_or_calculation_is_rejected(self):
        data = pc.materials(pc.ROOT, CASE)
        for corruption in ["evidence", "calculation"]:
            with tempfile.TemporaryDirectory() as temp:
                root = Path(temp)
                for path in data["artifact_hashes"]:
                    dest = root/path
                    dest.parent.mkdir(parents=True, exist_ok=True)
                    dest.write_bytes((pc.ROOT/path).read_bytes())
                refpath = root/data["case"]["judge_only_artifacts"]["reference"]
                reference = json.loads(refpath.read_text())
                if corruption == "evidence":
                    reference["facts"][0]["supporting_spans"] = ["Invented source passage"]
                else:
                    reference["calculations"][0]["expected_fraction"] = "123"
                refpath.write_text(json.dumps(reference))
                with self.subTest(corruption=corruption), self.assertRaises(ValueError):
                    pc.materials(root, CASE)

    def test_judge_artifact_cannot_be_supplied_as_a_candidate_artifact(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            data = pc.materials(pc.ROOT, CASE)
            for path in data["artifact_hashes"]:
                dest = root/path
                dest.parent.mkdir(parents=True, exist_ok=True)
                dest.write_bytes((pc.ROOT/path).read_bytes())
            case = data["case"]
            case["candidate_artifacts"]["brief"] = case["judge_only_artifacts"]["reference"]
            (root/CASE).write_text(json.dumps(case))
            with self.assertRaisesRegex(ValueError, "overlap"):
                pc.materials(root, CASE)

    def test_request_order_hidden_calls_and_owner_subset_cannot_drift(self):
        original_read = pc.read
        plan = json.loads(original_read(pc.ROOT, str(pc.PLAN))[1])
        for corrupt in ["count", "hidden", "order", "owner", "budget"]:
            changed = copy.deepcopy(plan)
            batch = changed["proposed_first_batch"]
            if corrupt == "count":
                batch["candidate_generation_requests"] += 1
            elif corrupt == "hidden":
                batch["additional_inference_requests"] = 1
            elif corrupt == "order":
                batch["proposed_order"][0]["observations"][1] = batch["proposed_order"][0]["observations"][0]
            elif corrupt == "owner":
                batch["owner_review"]["pairs_specification"][0]["seed"] = 999
            else:
                batch["total_safety_seconds"] -= 1

            def read(root, path):
                if path == str(pc.PLAN):
                    return pc.ROOT/pc.PLAN, json.dumps(changed)
                return original_read(root, path)

            with self.subTest(corrupt=corrupt), patch.object(pc, "read", side_effect=read):
                with self.assertRaises(ValueError):
                    pc.audit(pc.ROOT, str(pc.PLAN))


class CalibrationJudgmentTests(unittest.TestCase):
    def setUp(self):
        self.data = pc.materials(pc.ROOT, CASE)
        self.answer = "Die allgemeine Freigabe ist bereits erteilt."
        self.result = {"schema_version": "practical-calibration-judgment-v1",
                       "case_id": self.data["case"]["case_id"], "candidate_id": "opaque-7",
                       "answer_sha256": hashlib.sha256(self.answer.encode()).hexdigest(),
                       "dimension_ratings": {d["id"]: {"rating": 3, "rationale": "Bound test judgment"}
                                             for d in self.data["rubric"]["dimensions"]},
                       "critical_findings": [], "usable_as_delivered": True,
                       "overall_reason": "Fixture checks structural integrity, not a real evaluation."}

    def test_points_are_computed_and_do_not_claim_semantic_proof(self):
        outcome = pc.judgment(self.result, self.answer, self.data)
        self.assertEqual(outcome["points"], 75)
        self.assertFalse(outcome["semantic_correctness_proven"])

    def test_material_error_stays_visible_even_with_high_points(self):
        self.result["critical_findings"] = [{"fact_id": "A-operation", "source_ids": ["D5"],
                                             "answer_quote": self.answer,
                                             "explanation": "D5 approves only the restricted pilot."}]
        self.result["usable_as_delivered"] = False
        outcome = pc.judgment(self.result, self.answer, self.data)
        self.assertEqual(outcome["points"], 75)
        self.assertFalse(outcome["usable_as_delivered"])
        self.result["usable_as_delivered"] = True
        with self.assertRaises(ValueError):
            pc.judgment(self.result, self.answer, self.data)

    def test_invented_answer_quotes_or_sources_cannot_support_critical_findings(self):
        base = {"fact_id": "A-operation", "source_ids": ["D5"], "answer_quote": self.answer,
                "explanation": "Contradicts restricted scope."}
        for change in [{"answer_quote": "Invented answer passage"}, {"fact_id": "missing"},
                       {"source_ids": ["D1"]}, {"answer_quote": ""}, {"source_ids": []}]:
            result = copy.deepcopy(self.result)
            result.update(usable_as_delivered=False, critical_findings=[{**base, **change}])
            with self.subTest(change=change), self.assertRaises(ValueError):
                pc.judgment(result, self.answer, self.data)

    def test_wrong_answer_hash_missing_dimension_and_boolean_rating_are_rejected(self):
        for corrupt in ["hash", "dimension", "boolean", "quote"]:
            result = copy.deepcopy(self.result)
            first = next(iter(result["dimension_ratings"]))
            if corrupt == "hash":
                result["answer_sha256"] = "0"*64
            elif corrupt == "dimension":
                result["dimension_ratings"].pop(first)
            elif corrupt == "boolean":
                result["dimension_ratings"][first]["rating"] = True
            else:
                result["dimension_ratings"][first]["evidence_quotes"] = ["not in actual answer"]
            with self.subTest(corrupt=corrupt), self.assertRaises(ValueError):
                pc.judgment(result, self.answer, self.data)


if __name__ == "__main__":
    unittest.main()
