from __future__ import annotations

import hashlib
import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from local_llm_benchmark.multi_format_transfer_artifacts import (
    ARTIFACTS,
    MAX_RESPONSE_BYTES,
    ArtifactToolError,
    execute_artifact_request,
    verify_workspace,
)
from local_llm_benchmark.runner import load_json


REPO_ROOT = Path(__file__).resolve().parents[1]
FIXTURE_ROOT = REPO_ROOT / "tasks/agentic/multi-format-document-analysis/supplier-award-reconciliation/fixture"
CANONICAL_PATH = REPO_ROOT / "tasks/agentic/multi-format-document-analysis/supplier-award-reconciliation/canonical/canonical-extraction-v0.2.json"
BACKEND_PATH = REPO_ROOT / "local_llm_benchmark/multi_format_transfer_artifacts.py"
PDFTOTEXT = Path(shutil.which("pdftotext") or "")


class MultiFormatTransferArtifactToolTests(unittest.TestCase):
    def _all_records(self, workspace: Path = FIXTURE_ROOT) -> list[dict[str, object]]:
        records = []
        for definition in ARTIFACTS.values():
            operation = {"docx": "read_docx", "pdf": "read_pdf", "xlsx": "read_xlsx"}[definition["format"]]
            for query in definition["queries"]:
                result = execute_artifact_request(workspace, {"operation": operation, **query}, pdftotext_path=PDFTOTEXT)
                records.append(result["record"])
        return records

    def test_every_live_binary_record_matches_frozen_canonical_extraction(self) -> None:
        self.assertEqual(self._all_records(), load_json(CANONICAL_PATH)["evidence_records"])

    def test_inventory_is_bounded_and_frozen(self) -> None:
        result = execute_artifact_request(FIXTURE_ROOT, {"operation": "list_artifacts"}, pdftotext_path=PDFTOTEXT)
        self.assertEqual(result["api_version"], "0.2.0")
        self.assertEqual([item["filename"] for item in result["artifacts"]], list(ARTIFACTS))
        self.assertLessEqual(len(json.dumps(result, ensure_ascii=False).encode("utf-8")), MAX_RESPONSE_BYTES)
        self.assertEqual(sum(len(item["available_queries"]) for item in result["artifacts"]), 16)

    def test_reads_preserve_every_artifact_byte(self) -> None:
        before = {path.name: hashlib.sha256(path.read_bytes()).hexdigest() for path in FIXTURE_ROOT.iterdir()}
        self._all_records()
        after = {path.name: hashlib.sha256(path.read_bytes()).hexdigest() for path in FIXTURE_ROOT.iterdir()}
        self.assertEqual(before, after)

    def test_unlisted_queries_paths_and_workspace_files_fail_closed(self) -> None:
        for request, code in (
            ({"operation": "read_docx", "anchor": "../reference"}, "unknown_anchor"),
            ({"operation": "read_pdf", "page": 1, "element": "text"}, "unknown_anchor"),
            ({"operation": "read_xlsx", "sheet": "Dashboard", "range": "A1:Z99"}, "unknown_anchor"),
            ({"operation": "list_artifacts", "path": "secret"}, "invalid_arguments"),
            ({"operation": "shell"}, "unsupported_operation"),
        ):
            with self.subTest(request=request):
                with self.assertRaises(ArtifactToolError) as raised:
                    execute_artifact_request(FIXTURE_ROOT, request, pdftotext_path=PDFTOTEXT)
                self.assertEqual(raised.exception.code, code)
        with tempfile.TemporaryDirectory() as temporary:
            workspace = Path(temporary)
            for filename in ARTIFACTS:
                shutil.copyfile(FIXTURE_ROOT / filename, workspace / filename)
            (workspace / "hidden.json").write_text("{}", encoding="utf-8")
            with self.assertRaisesRegex(ArtifactToolError, "exactly"):
                verify_workspace(workspace)

    def test_symlink_and_binary_mutation_are_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            workspace = Path(temporary)
            for filename in ARTIFACTS:
                shutil.copyfile(FIXTURE_ROOT / filename, workspace / filename)
            target = workspace / "supplier-selection-policy.docx"
            target.unlink()
            target.symlink_to(FIXTURE_ROOT / target.name)
            with self.assertRaises(ArtifactToolError) as raised:
                verify_workspace(workspace)
            self.assertEqual(raised.exception.code, "unsafe_artifact")
        with tempfile.TemporaryDirectory() as temporary:
            workspace = Path(temporary)
            for filename in ARTIFACTS:
                shutil.copyfile(FIXTURE_ROOT / filename, workspace / filename)
            with (workspace / "bid-evaluation.xlsx").open("ab") as stream:
                stream.write(b"mutation")
            with self.assertRaises(ArtifactToolError) as raised:
                execute_artifact_request(workspace, {"operation": "list_artifacts"}, pdftotext_path=PDFTOTEXT)
            self.assertEqual(raised.exception.code, "artifact_identity_mismatch")

    def test_standalone_bridge_matches_direct_backend(self) -> None:
        request = {"operation": "read_pdf", "page": 3, "element": "note=Signed-final"}
        completed = subprocess.run(
            [sys.executable, "-I", "-B", str(BACKEND_PATH), "--workspace", str(FIXTURE_ROOT), "--pdftotext", str(PDFTOTEXT)],
            input=json.dumps(request), capture_output=True, text=True, check=True,
        )
        self.assertEqual(json.loads(completed.stdout), execute_artifact_request(FIXTURE_ROOT, request, pdftotext_path=PDFTOTEXT))
        source = BACKEND_PATH.read_text(encoding="utf-8")
        self.assertNotIn("ground-truth-v0.2.json", source)
        self.assertNotIn("canonical-extraction-v0.2.json", source)


if __name__ == "__main__":
    unittest.main()
