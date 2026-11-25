import copy
import hashlib
import json
import unittest

from local_llm_benchmark import practical_calibration as pc
from local_llm_benchmark import practical_text_review as review


CASE = "tasks/calibration/practical-profiles-v0.1/document-decision/calibration-case.json"


class SeparateTextReviewTests(unittest.TestCase):
    def setUp(self):
        self.data = pc.materials(pc.ROOT, CASE)
        self.answer = "Die allgemeine Freigabe ist bereits erteilt."
        self.legacy = {
            "schema_version": "practical-calibration-judgment-v1",
            "case_id": self.data["case"]["case_id"], "candidate_id": "fixture-only",
            "answer_sha256": hashlib.sha256(self.answer.encode()).hexdigest(),
            "dimension_ratings": {d["id"]: {"rating": 3, "rationale": "Synthetic fixture, no semantic assessment."}
                                  for d in self.data["rubric"]["dimensions"]},
            "critical_findings": [{"fact_id": "A-operation", "source_ids": ["D5"],
                                   "answer_quote": self.answer,
                                   "explanation": "Only a restricted pilot is authorized."}],
            "usable_as_delivered": False, "overall_reason": "Structural test fixture."}
        self.freeze()

    def freeze(self):
        self.original = json.dumps(self.legacy, ensure_ascii=False).encode()
        self.value = {
            "schema_version": "practical-text-review-v0.2",
            "case_id": self.legacy["case_id"], "candidate_id": "fixture-only",
            "answer_sha256": self.legacy["answer_sha256"],
            "as_delivered_origin": "frozen_v1",
            "v1_judgment_sha256": hashlib.sha256(self.original).hexdigest(),
            "as_delivered": copy.deepcopy(self.legacy),
            "reading_profile": dict.fromkeys(review.READING_DIMENSIONS),
            "editing_base": {"status": "not_assessed", "verdict": None, "rationale": None,
                             "required_repairs": [], "remaining_uncertainties": [],
                             "post_edit_quality": "not_evaluated"}}

    def editing_assessed(self, verdict="conditional"):
        self.value["editing_base"].update(
            status="assessed", verdict=verdict,
            rationale="Could be a base after factual repair; no edited result measured.",
            required_repairs=[{"kind": "factual_correction", "answer_quote": self.answer,
                               "fact_ids": ["A-operation"],
                               "change": "Restrict the claim to the authorized pilot."}])

    def check(self):
        return review.check_review(self.value, self.answer, self.data, self.original)

    def test_legacy_quality_is_preserved_and_unknown_editing_is_not_zero(self):
        result = self.check()
        self.assertEqual(result["as_delivered"], pc.judgment(self.legacy, self.answer, self.data))
        self.assertIsNone(result["editing_base"]["verdict"])
        self.assertTrue(all(v is None for v in result["reading_profile"].values()))
        self.assertIsNone(result["combined_score"])
        self.assertFalse(result["semantic_correctness_proven"])

    def test_conditional_editing_base_does_not_erase_raw_factual_failure(self):
        self.editing_assessed()
        result = self.check()
        self.assertEqual(result["editing_base"]["verdict"], "conditional")
        self.assertFalse(result["as_delivered"]["usable_as_delivered"])
        self.assertEqual(result["as_delivered"]["critical_findings"], 1)
        self.assertEqual(result["editing_base"]["post_edit_quality"], "not_evaluated")

    def test_frozen_result_cannot_be_silently_rescored_or_relabelled(self):
        for field in ["rating", "digest", "boolean_extra"]:
            self.freeze()
            if field == "rating":
                self.value["as_delivered"]["dimension_ratings"]["language"]["rating"] = 4
            elif field == "digest":
                self.value["v1_judgment_sha256"] = "0" * 64
            else:
                self.legacy["extra"] = 1
                self.freeze()
                self.value["as_delivered"]["extra"] = True
            with self.subTest(field=field), self.assertRaisesRegex(ValueError, "Frozen v1 judgment changed"):
                self.check()

    def test_frozen_provenance_requires_original_bytes(self):
        with self.assertRaisesRegex(ValueError, "bytes are required"):
            review.check_review(self.value, self.answer, self.data)

    def test_review_identity_cannot_be_joined_to_another_candidate_or_answer(self):
        for key in ["case_id", "candidate_id", "answer_sha256"]:
            self.freeze()
            self.value[key] = "0" * 64 if key == "answer_sha256" else "other"
            with self.subTest(key=key), self.assertRaisesRegex(ValueError, "binding differ"):
                self.check()

    def test_reading_evidence_must_exist_and_dimensions_stay_separate(self):
        self.value["reading_profile"]["fluency"] = {
            "rating": 3, "rationale": "Fixture assessment.", "evidence_quotes": [self.answer]}
        self.assertEqual(self.check()["reading_profile"]["fluency"]["rating"], 3)
        self.value["reading_profile"]["fluency"]["evidence_quotes"] = ["Invented passage"]
        with self.assertRaisesRegex(ValueError, "quote absent"):
            self.check()

    def test_missing_target_boolean_rating_and_fake_post_edit_success_rejected(self):
        for corrupt in ["target", "rating", "post_edit"]:
            self.freeze()
            if corrupt == "target":
                self.value.pop("editing_base")
            elif corrupt == "rating":
                self.value["reading_profile"]["grammar"] = {
                    "rating": True, "rationale": "Fixture", "evidence_quotes": [self.answer]}
            else:
                self.value["editing_base"]["post_edit_quality"] = "ready"
            with self.subTest(corrupt=corrupt), self.assertRaises(ValueError):
                self.check()

    def test_unassessed_target_cannot_claim_a_verdict_or_repair_plan(self):
        self.value["editing_base"]["verdict"] = "good"
        with self.assertRaisesRegex(ValueError, "must remain unknown"):
            self.check()

    def test_positive_editing_verdict_cannot_ignore_known_factual_defects(self):
        for corrupt in ["good", "no_repairs", "style_only", "wrong_fact"]:
            self.freeze()
            self.editing_assessed()
            if corrupt == "good":
                self.value["editing_base"]["verdict"] = "good"
            elif corrupt == "no_repairs":
                self.value["editing_base"]["required_repairs"] = []
            elif corrupt == "style_only":
                self.value["editing_base"]["required_repairs"][0]["kind"] = "structure"
            else:
                self.value["editing_base"]["required_repairs"][0]["fact_ids"] = ["A-time"]
            with self.subTest(corrupt=corrupt), self.assertRaisesRegex(ValueError, "critical facts"):
                self.check()

    def test_repair_must_have_real_evidence_and_known_reference(self):
        for corrupt in ["quote", "fact", "no_evidence"]:
            self.freeze()
            self.editing_assessed()
            repair = self.value["editing_base"]["required_repairs"][0]
            if corrupt == "quote":
                repair["answer_quote"] = "Invented passage"
            elif corrupt == "fact":
                repair["fact_ids"] = ["invented-fact"]
            else:
                repair.update(answer_quote=None, fact_ids=[])
            with self.subTest(corrupt=corrupt), self.assertRaises(ValueError):
                self.check()

    def test_new_review_cannot_claim_an_unbound_old_source(self):
        self.value["as_delivered_origin"] = "new_review"
        with self.assertRaisesRegex(ValueError, "must not claim"):
            self.check()
        self.value["v1_judgment_sha256"] = None
        result = review.check_review(self.value, self.answer, self.data)
        self.assertFalse(result["as_delivered"]["usable_as_delivered"])


if __name__ == "__main__":
    unittest.main()
