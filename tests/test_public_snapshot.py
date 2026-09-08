from __future__ import annotations

import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from scripts.audit_public_snapshot import audit
from scripts.export_public_snapshot import is_public
from scripts.prepare_public_release import (
    canonical_remote,
    sync_snapshot,
    tree_fingerprint,
)
from scripts.run_public_tests import PUBLIC_TEST_MODULES, REPO_ROOT


class PublicSnapshotPolicyTests(unittest.TestCase):
    def test_public_project_artifacts_are_included(self) -> None:
        self.assertTrue(is_public("CHANGELOG.md"))
        self.assertTrue(is_public("README.md"))
        self.assertTrue(is_public("PUBLICATION.md"))
        self.assertTrue(is_public("RELEASING.md"))
        self.assertTrue(is_public("local_llm_benchmark/runner.py"))
        self.assertTrue(is_public("tasks/general-knowledge/README.md"))
        self.assertTrue(is_public("reports/overview.md"))
        self.assertTrue(is_public("docs/benchmark-design.md"))

    def test_local_research_material_is_excluded(self) -> None:
        self.assertFalse(is_public("PROJECT_STATUS.md"))
        self.assertFalse(is_public("docs/case-study-log.md"))
        self.assertFalse(is_public("docs/case-study-writing-agent-brief.md"))
        self.assertFalse(is_public("docs/case-study-assets/screenshot.png"))
        self.assertFalse(is_public("data/private/source.md"))
        self.assertFalse(is_public("results/raw/run.json"))

    def test_audit_accepts_small_linked_public_tree(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "docs").mkdir()
            (root / "README.md").write_text(
                "[Method](docs/method.md)\n", encoding="utf-8"
            )
            (root / "docs/method.md").write_text("# Method\n", encoding="utf-8")

            self.assertEqual(audit(root), [])

    def test_audit_rejects_private_content_and_broken_links(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory)
            synthetic_email = "private" + chr(64) + "example.test"
            (root / "README.md").write_text(
                f"Contact {synthetic_email}. [Missing](missing.md)\n",
                encoding="utf-8",
            )
            private = root / "data/private"
            private.mkdir(parents=True)
            (private / "source.md").write_text("private\n", encoding="utf-8")

            details = {finding.detail for finding in audit(root)}
            self.assertIn("matched email address pattern", details)
            self.assertIn("broken local link: missing.md", details)
            self.assertIn("path is outside the public boundary", details)

    def test_audit_rejects_an_escaping_directory_symlink(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory) / "snapshot"
            root.mkdir()
            (root / "external").symlink_to(Path(directory).parent)

            details = {finding.detail for finding in audit(root)}
            self.assertIn("symlink escapes the snapshot", details)

    def test_public_test_modules_exist(self) -> None:
        for module in PUBLIC_TEST_MODULES:
            with self.subTest(module=module):
                relative = Path(*module.split(".")).with_suffix(".py")
                self.assertTrue((REPO_ROOT / relative).is_file())

    def test_remote_spellings_are_compared_by_repository(self) -> None:
        ssh = "git" + chr(64) + "github.com:Example/Benchmark.git"
        https = "https://github.com/example/benchmark"
        self.assertEqual(canonical_remote(ssh), canonical_remote(https))

    def test_release_sync_updates_adds_and_removes_tracked_files(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory)
            snapshot = root / "snapshot"
            public_clone = root / "public"
            snapshot.mkdir()
            public_clone.mkdir()

            (snapshot / "keep.txt").write_text("new\n", encoding="utf-8")
            (snapshot / "added.txt").write_text("added\n", encoding="utf-8")
            (public_clone / "keep.txt").write_text("old\n", encoding="utf-8")
            (public_clone / "removed.txt").write_text("old\n", encoding="utf-8")

            sync_snapshot(
                snapshot,
                public_clone,
                ["keep.txt", "removed.txt"],
            )

            self.assertEqual(
                (public_clone / "keep.txt").read_text(encoding="utf-8"),
                "new\n",
            )
            self.assertEqual(
                (public_clone / "added.txt").read_text(encoding="utf-8"),
                "added\n",
            )
            self.assertFalse((public_clone / "removed.txt").exists())

    def test_tree_fingerprint_detects_test_side_effects(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory)
            artifact = root / "artifact.txt"
            artifact.write_text("before\n", encoding="utf-8")
            before = tree_fingerprint(root)

            artifact.write_text("after\n", encoding="utf-8")

            self.assertNotEqual(tree_fingerprint(root), before)


if __name__ == "__main__":
    unittest.main()
