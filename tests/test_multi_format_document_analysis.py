from __future__ import annotations

import copy
import hashlib
import html
import json
import re
import unittest
import zipfile
from pathlib import Path

from local_llm_benchmark.multi_format_document_analysis import (
    EXPECTED_CHECK_IDS,
    load_multi_format_case,
    verify_multi_format_report,
)
from local_llm_benchmark.json_schema import validate_json
from local_llm_benchmark.runner import load_json


REPO_ROOT = Path(__file__).resolve().parents[1]
CASE_PATH = Path(
    "tasks/agentic/multi-format-document-analysis/"
    "rollout-readiness-reconciliation/case-v0.1.json"
)
QUALIFICATION_PATH = REPO_ROOT / (
    "tasks/agentic/multi-format-document-analysis/"
    "multi-format-v0.1-offline-qualification.json"
)
XLSX_QUALIFICATION_PATH = REPO_ROOT / (
    "tasks/agentic/multi-format-document-analysis/"
    "rollout-readiness-reconciliation/xlsx-artifact-qualification-v0.1.json"
)
DOCX_QUALIFICATION_PATH = REPO_ROOT / (
    "tasks/agentic/multi-format-document-analysis/"
    "rollout-readiness-reconciliation/docx-artifact-qualification-v0.1.json"
)
PDF_QUALIFICATION_PATH = REPO_ROOT / (
    "tasks/agentic/multi-format-document-analysis/"
    "rollout-readiness-reconciliation/pdf-artifact-qualification-v0.1.json"
)
CANONICAL_QUALIFICATION_PATH = REPO_ROOT / (
    "tasks/agentic/multi-format-document-analysis/"
    "rollout-readiness-reconciliation/"
    "canonical-extraction-qualification-v0.1.json"
)


def failed_ids(result: dict[str, object]) -> set[str]:
    return {
        item["check_id"]
        for item in result["checks"]
        if not item["passed"]
    }


class MultiFormatDocumentAnalysisTests(unittest.TestCase):
    def setUp(self) -> None:
        self.loaded = load_multi_format_case(REPO_ROOT, CASE_PATH)
        self.reference = load_json(self.loaded["reference_report_path"])

    def test_measured_execution_completion_preserves_pre_execution_case_state(self) -> None:
        case = self.loaded["case"]
        self.assertEqual(
            case["status"], "harness_qualified_smokes_frozen_pending_resource_window"
        )
        self.assertFalse(case["live_execution_authorized"])
        self.assertTrue(case["artifact_generation_complete"])
        self.assertTrue(case["canonical_extraction_complete"])

        qualification = load_json(QUALIFICATION_PATH)
        self.assertEqual(
            qualification["status"],
            "targeted_qwen38_confirmation_complete",
        )
        self.assertTrue(qualification["live_inference_performed"])
        self.assertTrue(qualification["live_execution_authorized"])
        self.assertNotIn(
            "freeze binary hashes and tool/runtime versions",
            qualification["blocking_gates"],
        )
        self.assertNotIn(
            "create and reconcile canonical extractions against visual source truth",
            qualification["blocking_gates"],
        )
        self.assertNotIn(
            "qualify the read-only artifact tool surface",
            qualification["blocking_gates"],
        )
        self.assertNotIn(
            "run one excluded harness smoke per admitted complete system",
            qualification["blocking_gates"],
        )
        self.assertEqual(
            qualification["frozen_measured_plan"]["sha256"],
            "822074b8abfe631bf7c1f63dcdcc03af24d81a7dd3a260722ceec4a485b26389",
        )
        self.assertEqual(qualification["blocking_gates"], [])
        measured = qualification["completed_measured_study"]
        self.assertEqual(measured["terminal_cell_count"], 15)
        self.assertEqual(measured["semantic_verified_success_count"], 2)
        self.assertEqual(measured["strict_transport_compliance_count"], 12)
        self.assertEqual(measured["resource_gates_passed"], 15)
        self.assertEqual(
            measured["pi_cells_with_fresh_12_check_seatbelt_acceptance"], 5
        )
        self.assertTrue(measured["ollama_postflight_empty"])
        self.assertEqual(measured["automatic_retries"], 0)
        confirmation = qualification["completed_targeted_confirmation"]
        self.assertEqual(confirmation["terminal_cell_count"], 9)
        self.assertEqual(confirmation["semantic_verified_success_count"], 5)
        self.assertEqual(confirmation["strict_transport_compliance_count"], 6)
        self.assertEqual(confirmation["resource_gates_passed"], 9)
        self.assertEqual(
            confirmation["pi_cells_with_fresh_12_check_seatbelt_acceptance"], 3
        )
        self.assertEqual(confirmation["scheduled_repetitions_per_condition"], 3)
        self.assertFalse(confirmation["historical_cells_reused"])
        self.assertTrue(confirmation["ollama_postflight_empty"])
        self.assertEqual(confirmation["automatic_retries"], 0)

    def test_two_conditions_keep_model_reasoning_and_artifact_access_separate(self) -> None:
        conditions = self.loaded["case"]["evaluation_conditions"]
        self.assertEqual(
            [item["condition_id"] for item in conditions],
            ["canonical-representation", "real-artifact-harness"],
        )
        self.assertEqual([item["track"] for item in conditions], ["A", "B"])
        self.assertEqual(
            [item["artifact_tooling_is_part_of_identity"] for item in conditions],
            [False, True],
        )

    def test_qualified_xlsx_hash_formulas_and_cached_values_are_frozen(self) -> None:
        qualification = load_json(XLSX_QUALIFICATION_PATH)
        artifact = qualification["artifact"]
        workbook_path = REPO_ROOT / artifact["path"]
        workbook_bytes = workbook_path.read_bytes()

        self.assertEqual(qualification["status"], "qualified")
        self.assertFalse(qualification["live_inference_performed"])
        self.assertEqual(len(workbook_bytes), artifact["size_bytes"])
        self.assertEqual(
            hashlib.sha256(workbook_bytes).hexdigest(),
            artifact["sha256"],
        )
        for reproducibility_input in qualification["reproducibility_inputs"]:
            input_bytes = (REPO_ROOT / reproducibility_input["path"]).read_bytes()
            self.assertEqual(
                hashlib.sha256(input_bytes).hexdigest(),
                reproducibility_input["sha256"],
            )
        amendment_path = (
            REPO_ROOT / qualification["authoring_protocol"]["amendment_path"]
        )
        self.assertEqual(
            hashlib.sha256(amendment_path.read_bytes()).hexdigest(),
            qualification["authoring_protocol"]["amendment_sha256"],
        )
        offline_qualification = load_json(QUALIFICATION_PATH)
        self.assertIn(
            {
                "format": "xlsx",
                "path": artifact["path"],
                "sha256": artifact["sha256"],
                "qualification_path": XLSX_QUALIFICATION_PATH.relative_to(
                    REPO_ROOT
                ).as_posix(),
            },
            offline_qualification["qualified_artifact_records"],
        )

        with zipfile.ZipFile(workbook_path) as archive:
            self.assertIsNone(archive.testzip())
            members = set(archive.namelist())
            self.assertFalse(
                any(name.startswith("xl/externalLinks/") for name in members)
            )
            self.assertNotIn("xl/vbaProject.bin", members)
            workbook = archive.read("xl/workbook.xml")
            self.assertEqual(
                [
                    name.decode("utf-8")
                    for name in re.findall(rb'<sheet name="([^"]+)"', workbook)
                ],
                ["Summary", "Capacity"],
            )
            summary = archive.read("xl/worksheets/sheet1.xml")
            capacity = archive.read("xl/worksheets/sheet2.xml")

        def cell_text(sheet: bytes, reference: str, tag: str) -> str | None:
            cell = re.search(
                rb'<c\b[^>]*\br="'
                + re.escape(reference.encode("ascii"))
                + rb'"[^>]*>(.*?)</c>',
                sheet,
                re.DOTALL,
            )
            self.assertIsNotNone(cell, reference)
            value = re.search(
                rb'<'
                + tag.encode("ascii")
                + rb'(?:\s[^>]*)?>(.*?)</'
                + tag.encode("ascii")
                + rb'>',
                cell.group(1),
                re.DOTALL,
            )
            if value is None:
                return None
            return html.unescape(value.group(1).decode("utf-8"))

        self.assertEqual(
            cell_text(summary, "B3", "f"),
            'IF(AND(B4>=$F$4,B5<=$F$5,B6>=$F$6),"GO","HOLD")',
        )
        self.assertEqual(cell_text(summary, "B3", "v"), "GO")
        self.assertEqual(cell_text(summary, "B6", "v"), "1.35604395604396")

        expected_capacity_formulas = {
            "D4": "IFERROR(B4/C4,0)",
            "E4": 'IF(D4>=$H$3,"PASS","HOLD")',
            "D5": "IFERROR(B5/C5,0)",
            "E5": 'IF(D5>=$H$3,"PASS","HOLD")',
            "D6": "IFERROR(B6/C6,0)",
            "E6": 'IF(D6>=$H$3,"PASS","HOLD")',
            "D7": "IFERROR(B7/C7,0)",
            "E7": 'IF(D7>=$H$3,"PASS","HOLD")',
        }
        self.assertEqual(
            {
                reference: cell_text(capacity, reference, "f")
                for reference in expected_capacity_formulas
            },
            expected_capacity_formulas,
        )
        self.assertEqual(
            [cell_text(capacity, f"E{row}", "v") for row in range(4, 8)],
            ["PASS", "PASS", "PASS", "PASS"],
        )

    def test_qualified_docx_hash_structure_and_policy_facts_are_frozen(self) -> None:
        qualification = load_json(DOCX_QUALIFICATION_PATH)
        artifact = qualification["artifact"]
        document_path = REPO_ROOT / artifact["path"]
        document_bytes = document_path.read_bytes()

        self.assertEqual(qualification["status"], "qualified")
        self.assertFalse(qualification["live_inference_performed"])
        self.assertEqual(len(document_bytes), artifact["size_bytes"])
        self.assertEqual(
            hashlib.sha256(document_bytes).hexdigest(),
            artifact["sha256"],
        )
        for reproducibility_input in qualification["reproducibility_inputs"]:
            input_bytes = (REPO_ROOT / reproducibility_input["path"]).read_bytes()
            self.assertEqual(
                hashlib.sha256(input_bytes).hexdigest(),
                reproducibility_input["sha256"],
            )
        amendment_path = (
            REPO_ROOT / qualification["authoring_protocol"]["amendment_path"]
        )
        self.assertEqual(
            hashlib.sha256(amendment_path.read_bytes()).hexdigest(),
            qualification["authoring_protocol"]["amendment_sha256"],
        )
        offline_qualification = load_json(QUALIFICATION_PATH)
        self.assertIn(
            {
                "format": "docx",
                "path": artifact["path"],
                "sha256": artifact["sha256"],
                "qualification_path": DOCX_QUALIFICATION_PATH.relative_to(
                    REPO_ROOT
                ).as_posix(),
            },
            offline_qualification["qualified_artifact_records"],
        )

        with zipfile.ZipFile(document_path) as archive:
            self.assertIsNone(archive.testzip())
            members = set(archive.namelist())
            self.assertNotIn("word/vbaProject.bin", members)
            self.assertFalse(
                any(name.startswith("word/comments") for name in members)
            )
            for relationship_path in (
                name for name in members if name.endswith(".rels")
            ):
                self.assertNotIn(
                    b'TargetMode="External"', archive.read(relationship_path)
                )
            document_xml = archive.read("word/document.xml")
            styles_xml = archive.read("word/styles.xml")
            numbering_xml = archive.read("word/numbering.xml")
            footer_xml = archive.read("word/footer1.xml")
            core_xml = archive.read("docProps/core.xml")

        def xml_text(fragment: bytes) -> str:
            return "".join(
                html.unescape(value.decode("utf-8"))
                for value in re.findall(
                    rb"<w:t(?:\s[^>]*)?>(.*?)</w:t>",
                    fragment,
                    re.DOTALL,
                )
            )

        headings = []
        for paragraph in re.findall(
            rb"<w:p(?:\s[^>]*)?>(.*?)</w:p>", document_xml, re.DOTALL
        ):
            style = re.search(rb'<w:pStyle w:val="(Heading[123])"', paragraph)
            if style:
                headings.append((xml_text(paragraph), style.group(1).decode("ascii")))
        self.assertEqual(
            headings,
            [
                ("Regional gates", "Heading1"),
                ("Decision rule", "Heading1"),
                ("Decision procedure", "Heading2"),
                ("Phased release", "Heading1"),
                ("Evidence cutoff", "Heading1"),
            ],
        )
        self.assertEqual(
            set(
                name.decode("utf-8")
                for name in re.findall(
                    rb'<w:bookmarkStart[^>]*w:name="([^"]+)"', document_xml
                )
            ),
            {"Regional_gates", "Decision_rule", "Phased_release", "Evidence_cutoff"},
        )
        self.assertIn(b'<w:tblCaption w:val="Regional-gates"', document_xml)
        self.assertEqual(
            [
                int(value)
                for value in re.findall(rb'<w:gridCol w:w="(\d+)"', document_xml)
            ],
            [1760, 2720, 1760, 3120],
        )
        self.assertIn(b'<w:pgSz w:w="12240" w:h="15840"', document_xml)
        self.assertIn(
            b'w:top="1440" w:right="1440" w:bottom="1440" w:left="1440"',
            document_xml,
        )
        self.assertIn(b'<w:style w:type="paragraph" w:styleId="Heading1"', styles_xml)
        self.assertIn(b'<w:ind w:left="720" w:hanging="360"', numbering_xml)
        self.assertEqual(
            {
                instruction.strip().decode("ascii")
                for instruction in re.findall(
                    rb"<w:instrText[^>]*>(.*?)</w:instrText>", footer_xml
                )
            },
            {"PAGE", "NUMPAGES"},
        )
        self.assertIn(
            b"<dc:creator>Local LLM Benchmark Lab</dc:creator>", core_xml
        )

        visible_text = xml_text(document_xml)
        for required_fragment in (
            "Completion is at least 95%.",
            "Open Sev-1 issue count equals 0.",
            "Open Sev-2 issue count is at most 2.",
            "Support capacity / projected peak load is at least 1.25.",
            "Portfolio averages, rollups or dashboard status cannot replace or override a failed regional gate.",
            "A phased production launch may proceed when at least one region passes all four gates.",
            "Use evidence finalized no later than 2026-08-31 18:00 UTC.",
        ):
            self.assertIn(required_fragment, visible_text)

    def test_qualified_pdf_hash_structure_and_reliability_facts_are_frozen(self) -> None:
        qualification = load_json(PDF_QUALIFICATION_PATH)
        artifact = qualification["artifact"]
        document_path = REPO_ROOT / artifact["path"]
        document_bytes = document_path.read_bytes()

        self.assertEqual(qualification["status"], "qualified")
        self.assertFalse(qualification["live_inference_performed"])
        self.assertEqual(len(document_bytes), artifact["size_bytes"])
        self.assertEqual(
            hashlib.sha256(document_bytes).hexdigest(),
            artifact["sha256"],
        )
        for reproducibility_input in qualification["reproducibility_inputs"]:
            input_bytes = (REPO_ROOT / reproducibility_input["path"]).read_bytes()
            self.assertEqual(
                hashlib.sha256(input_bytes).hexdigest(),
                reproducibility_input["sha256"],
            )
        amendment_path = (
            REPO_ROOT / qualification["authoring_protocol"]["amendment_path"]
        )
        self.assertEqual(
            hashlib.sha256(amendment_path.read_bytes()).hexdigest(),
            qualification["authoring_protocol"]["amendment_sha256"],
        )
        offline_qualification = load_json(QUALIFICATION_PATH)
        self.assertIn(
            {
                "format": "pdf",
                "path": artifact["path"],
                "sha256": artifact["sha256"],
                "qualification_path": PDF_QUALIFICATION_PATH.relative_to(
                    REPO_ROOT
                ).as_posix(),
            },
            offline_qualification["qualified_artifact_records"],
        )

        self.assertTrue(document_bytes.startswith(b"%PDF-1.4"))
        for required_fragment in (
            b"/Author (Local LLM Benchmark Lab)",
            b"/Creator (ReportLab 5.0.1)",
            b"/Title (Regional Reliability Review)",
            b"/Outlines",
            b"/Count 3",
        ):
            self.assertIn(required_fragment, document_bytes)
        for prohibited_fragment in (
            b"/AcroForm",
            b"/Encrypt",
            b"/JavaScript",
            b"/OpenAction",
        ):
            self.assertNotIn(prohibited_fragment, document_bytes)
        self.assertEqual(
            {
                item["fact_code"]
                for item in qualification["source_anchor_reconciliation"]
                if item["passed"]
            },
            {
                "REL-PRELIMINARY",
                "REL-FINAL",
                "REL-NORTH",
                "REL-CENTRAL",
                "REL-WEST",
                "REL-EAST",
            },
        )

    def test_canonical_extraction_is_frozen_complete_and_answer_neutral(self) -> None:
        qualification = load_json(CANONICAL_QUALIFICATION_PATH)
        extraction_record = qualification["extraction"]
        extraction_path = REPO_ROOT / extraction_record["path"]
        extraction_bytes = extraction_path.read_bytes()
        extraction = load_json(extraction_path)
        schema_record = qualification["schema"]
        schema_path = REPO_ROOT / schema_record["path"]
        schema_bytes = schema_path.read_bytes()

        self.assertEqual(qualification["status"], "qualified")
        self.assertFalse(qualification["live_inference_performed"])
        self.assertEqual(len(extraction_bytes), extraction_record["size_bytes"])
        self.assertEqual(
            hashlib.sha256(extraction_bytes).hexdigest(),
            extraction_record["sha256"],
        )
        self.assertEqual(
            hashlib.sha256(schema_bytes).hexdigest(),
            schema_record["sha256"],
        )
        validate_json(extraction, load_json(schema_path))
        for reproducibility_input in qualification["reproducibility_inputs"]:
            input_bytes = (REPO_ROOT / reproducibility_input["path"]).read_bytes()
            self.assertEqual(
                hashlib.sha256(input_bytes).hexdigest(),
                reproducibility_input["sha256"],
            )

        offline_record = load_json(QUALIFICATION_PATH)[
            "canonical_extraction_record"
        ]
        self.assertEqual(offline_record["path"], extraction_record["path"])
        self.assertEqual(offline_record["sha256"], extraction_record["sha256"])
        self.assertEqual(offline_record["schema_path"], schema_record["path"])
        self.assertEqual(offline_record["schema_sha256"], schema_record["sha256"])
        self.assertEqual(
            offline_record["qualification_path"],
            CANONICAL_QUALIFICATION_PATH.relative_to(REPO_ROOT).as_posix(),
        )
        self.assertEqual(self.loaded["canonical"], extraction)

        expected_identity = [
            (item["fact_code"], item["source_ref"], item["artifact"])
            for item in self.loaded["blueprint"]["facts"]
        ]
        observed_identity = [
            (item["fact_code"], item["source_ref"], item["artifact_format"])
            for item in extraction["evidence_records"]
        ]
        self.assertEqual(observed_identity, expected_identity)
        self.assertEqual(
            [item["filename"] for item in extraction["artifact_inputs"]],
            self.loaded["case"]["candidate_context"]["planned_files"],
        )
        self.assertEqual(
            {
                artifact_format: sum(
                    item["artifact_format"] == artifact_format
                    for item in extraction["evidence_records"]
                )
                for artifact_format in ("docx", "pdf", "xlsx")
            },
            {"docx": 4, "pdf": 6, "xlsx": 5},
        )

        records = {
            item["fact_code"]: item for item in extraction["evidence_records"]
        }
        self.assertIn("Completion is at least 95%.", records["POL-GATES"]["text"])
        self.assertIn("supersedes", records["REL-FINAL"]["text"])
        self.assertEqual(records["REL-CENTRAL"]["fields"][2]["value"], 3)
        self.assertEqual(records["REL-EAST"]["fields"][1]["value"], 1)
        self.assertEqual(
            records["CAP-NORTH"]["fields"][2]["formula"],
            "=IFERROR(B4/C4,0)",
        )
        self.assertEqual(records["DASH-STATUS"]["fields"][0]["value"], "GO")

        serialized = json.dumps(extraction, sort_keys=True)
        for prohibited in (
            "phased_go",
            "launch_north_only",
            "sev2_above_limit",
            "completion_below_threshold",
            "approved_regions",
            "blocked_regions",
            "recommended_actions",
        ):
            self.assertNotIn(prohibited, serialized)

    def test_blueprint_has_exactly_three_formats_and_unique_anchors(self) -> None:
        blueprint = self.loaded["blueprint"]
        self.assertEqual(
            {item["format"] for item in blueprint["artifacts"]},
            {"docx", "pdf", "xlsx"},
        )
        facts = blueprint["facts"]
        self.assertEqual(
            len({item["fact_code"] for item in facts}), len(facts)
        )
        self.assertEqual(
            len({item["source_ref"] for item in facts}), len(facts)
        )

    def test_reference_passes_all_eleven_checks(self) -> None:
        result = verify_multi_format_report(REPO_ROOT, CASE_PATH, self.reference)
        self.assertEqual(
            [item["check_id"] for item in result["checks"]],
            EXPECTED_CHECK_IDS,
        )
        self.assertEqual(result["essential_pass_count"], 11)
        self.assertTrue(result["semantic_verified_success"])
        self.assertTrue(result["supplemental_free_text_review_required"])

    def test_task_exposes_every_deterministic_check_marker(self) -> None:
        contract = self.loaded["contract"]
        task = self.loaded["task_path"].read_text(encoding="utf-8")
        self.assertEqual(
            [item["check_id"] for item in contract["essential_checks"]],
            EXPECTED_CHECK_IDS,
        )
        for item in contract["essential_checks"]:
            self.assertIn(item["visible_marker"], task)

    def test_planned_files_match_the_blueprint_exactly(self) -> None:
        self.assertEqual(
            set(self.loaded["case"]["candidate_context"]["planned_files"]),
            {item["filename"] for item in self.loaded["blueprint"]["artifacts"]},
        )
        self.assertEqual(
            self.loaded["case"]["output_contract"][
                "strict_json_transport_scored_separately"
            ],
            self.loaded["contract"]["strict_transport_scored_separately"],
        )

    def test_schema_failure_is_not_repaired_or_semantically_guessed(self) -> None:
        malformed = copy.deepcopy(self.reference)
        del malformed["decision"]
        result = verify_multi_format_report(REPO_ROOT, CASE_PATH, malformed)
        self.assertEqual(failed_ids(result), set(EXPECTED_CHECK_IDS))
        self.assertFalse(result["semantic_verified_success"])

    def test_decision_region_and_blocker_near_misses_fail(self) -> None:
        wrong_decision = copy.deepcopy(self.reference)
        wrong_decision["decision"]["code"] = "full_go"
        self.assertEqual(
            failed_ids(verify_multi_format_report(REPO_ROOT, CASE_PATH, wrong_decision)),
            {"decision"},
        )

        wrong_regions = copy.deepcopy(self.reference)
        wrong_regions["decision"]["approved_regions"] = ["north", "central"]
        self.assertEqual(
            failed_ids(verify_multi_format_report(REPO_ROOT, CASE_PATH, wrong_regions)),
            {"approved_regions"},
        )

        wrong_blocker = copy.deepcopy(self.reference)
        wrong_blocker["decision"]["blocked_regions"][0]["blocker_code"] = (
            "capacity_below_threshold"
        )
        self.assertEqual(
            failed_ids(verify_multi_format_report(REPO_ROOT, CASE_PATH, wrong_blocker)),
            {"region_blockers"},
        )

    def test_citation_and_required_evidence_are_independent(self) -> None:
        wrong_anchor = copy.deepcopy(self.reference)
        wrong_anchor["evidence"][0]["source_ref"] = "rollout-policy.docx#not-real"
        result = verify_multi_format_report(REPO_ROOT, CASE_PATH, wrong_anchor)
        self.assertEqual(failed_ids(result), {"citation_integrity"})

        missing_fact = copy.deepcopy(self.reference)
        missing_fact["evidence"] = [
            item for item in missing_fact["evidence"] if item["fact_code"] != "POL-CUTOFF"
        ]
        result = verify_multi_format_report(REPO_ROOT, CASE_PATH, missing_fact)
        self.assertEqual(failed_ids(result), {"required_evidence"})

    def test_cross_format_conflict_action_and_uncertainty_near_misses_fail(self) -> None:
        no_xlsx = copy.deepcopy(self.reference)
        no_xlsx["evidence"] = [
            item
            for item in no_xlsx["evidence"]
            if not item["source_ref"].startswith("regional-readiness.xlsx")
        ]
        result = verify_multi_format_report(REPO_ROOT, CASE_PATH, no_xlsx)
        self.assertEqual(
            failed_ids(result), {"required_evidence", "cross_format_coverage"}
        )

        no_conflict = copy.deepcopy(self.reference)
        no_conflict["conflicts"] = no_conflict["conflicts"][:1]
        self.assertEqual(
            failed_ids(verify_multi_format_report(REPO_ROOT, CASE_PATH, no_conflict)),
            {"conflict_resolution"},
        )

        no_action = copy.deepcopy(self.reference)
        no_action["recommended_actions"] = no_action["recommended_actions"][:-1]
        self.assertEqual(
            failed_ids(verify_multi_format_report(REPO_ROOT, CASE_PATH, no_action)),
            {"action_plan"},
        )

        no_uncertainty = copy.deepcopy(self.reference)
        no_uncertainty["uncertainties"] = no_uncertainty["uncertainties"][:-1]
        self.assertEqual(
            failed_ids(
                verify_multi_format_report(REPO_ROOT, CASE_PATH, no_uncertainty)
            ),
            {"uncertainty"},
        )

    def test_invented_controlled_value_fails_integrity(self) -> None:
        invented = copy.deepcopy(self.reference)
        invented["recommended_actions"].append(
            {"code": "invented_action", "rationale": "Not in the visible codebook."}
        )
        result = verify_multi_format_report(REPO_ROOT, CASE_PATH, invented)
        self.assertEqual(failed_ids(result), {"controlled_value_integrity"})

    def test_duplicate_blocker_or_conflict_does_not_hide_behind_set_equality(self) -> None:
        duplicate_blocker = copy.deepcopy(self.reference)
        duplicate_blocker["decision"]["blocked_regions"].append(
            copy.deepcopy(duplicate_blocker["decision"]["blocked_regions"][0])
        )
        self.assertEqual(
            failed_ids(
                verify_multi_format_report(REPO_ROOT, CASE_PATH, duplicate_blocker)
            ),
            {"region_blockers"},
        )

        duplicate_conflict = copy.deepcopy(self.reference)
        duplicate_conflict["conflicts"].append(
            copy.deepcopy(duplicate_conflict["conflicts"][0])
        )
        self.assertEqual(
            failed_ids(
                verify_multi_format_report(REPO_ROOT, CASE_PATH, duplicate_conflict)
            ),
            {"conflict_resolution"},
        )


if __name__ == "__main__":
    unittest.main()
