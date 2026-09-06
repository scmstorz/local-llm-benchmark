"""Deterministic Track A runner for bounded coding tasks."""

from __future__ import annotations

import json
import os
import platform
import re
import secrets
import shutil
import subprocess
import sys
import tempfile
import time
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path, PurePosixPath
from typing import Any

from .ollama import OllamaClient
from .runner import (
    RunnerError,
    find_model,
    git_commit,
    load_json,
    memory_total_bytes,
    nanoseconds_to_seconds,
    resolve_repo_path,
    sha256_file,
    sha256_text,
    tokens_per_second,
    utc_now,
    write_json,
)


DEFAULT_CODING_CASE_PATH = Path(
    "tasks/coding/dev/pagination-cycle-guard/case.json"
)
DEFAULT_WHOLE_FILE_CODING_CASE_PATH = Path(
    "tasks/coding/dev/pagination-cycle-guard/case-whole-file-v1.1.json"
)


@dataclass(frozen=True)
class CodingRunConfig:
    """Configuration for one direct, non-agentic coding attempt."""

    model: str
    case_path: Path = DEFAULT_CODING_CASE_PATH
    host: str = "http://127.0.0.1:11434"
    results_dir: Path = Path("results/coding-runs")
    temperature: float | None = None
    seed: int | None = None
    num_ctx: int | None = None
    num_predict: int | None = None
    think: bool | str | None = None
    keep_alive: str | None = None
    timeout_seconds: float | None = None
    defer_verification: bool = False


def _relative_posix_path(value: Any, context: str) -> str:
    if not isinstance(value, str) or not value:
        raise RunnerError(f"Expected a non-empty relative path for {context}")
    path = PurePosixPath(value)
    if path.is_absolute() or ".." in path.parts or value != path.as_posix():
        raise RunnerError(f"Unsafe or non-normalized path for {context}: {value!r}")
    return value


def _fixture_inventory(root: Path) -> dict[str, dict[str, Any]]:
    inventory: dict[str, dict[str, Any]] = {}
    for path in sorted(item for item in root.rglob("*") if item.is_file()):
        relative = path.relative_to(root).as_posix()
        if "__pycache__" in path.parts or path.suffix == ".pyc":
            continue
        inventory[relative] = {
            "sha256": sha256_file(path),
            "size_bytes": path.stat().st_size,
        }
    return inventory


def _matches_any(path: str, patterns: list[str]) -> bool:
    candidate = PurePosixPath(path)
    return any(candidate.match(pattern) for pattern in patterns)


def _artifact_contract(case: dict[str, Any]) -> dict[str, Any]:
    legacy = case.get("patch_contract")
    current = case.get("artifact_contract")
    if isinstance(legacy, dict) == isinstance(current, dict):
        raise RunnerError(
            "Coding case must define exactly one of patch_contract or "
            "artifact_contract"
        )
    contract = current if isinstance(current, dict) else legacy
    assert isinstance(contract, dict)
    artifact_format = contract.get("format")
    if artifact_format not in {"git_unified_diff", "whole_file_envelope"}:
        raise RunnerError(f"Unsupported coding artifact format: {artifact_format!r}")
    return contract


def load_coding_case(repo_root: Path, case_path: Path) -> dict[str, Any]:
    """Load and integrity-check one frozen Track A coding case."""
    resolved_case_path = resolve_repo_path(repo_root, case_path)
    case = load_json(resolved_case_path)
    if case.get("track") != "A":
        raise RunnerError("The direct coding runner accepts only Track A cases")

    required_strings = ("case_id", "case_version", "task_family", "task_path")
    for key in required_strings:
        if not isinstance(case.get(key), str) or not case[key]:
            raise RunnerError(f"Coding case must define {key}")

    fixture_config = case.get("fixture")
    candidate_context = case.get("candidate_context")
    artifact_contract = _artifact_contract(case)
    verification = case.get("verification")
    evaluation = case.get("evaluation")
    prompt = case.get("prompt")
    inference_defaults = case.get("inference_defaults")
    for value, name in (
        (fixture_config, "fixture"),
        (candidate_context, "candidate_context"),
        (verification, "verification"),
        (evaluation, "evaluation"),
        (prompt, "prompt"),
        (inference_defaults, "inference_defaults"),
    ):
        if not isinstance(value, dict):
            raise RunnerError(f"Coding case must define a {name} object")

    fixture_root = resolve_repo_path(repo_root, fixture_config.get("root", ""))
    if not fixture_root.is_dir():
        raise RunnerError(f"Coding fixture does not exist: {fixture_root}")
    manifest_path = resolve_repo_path(
        repo_root, fixture_config.get("manifest_path", "")
    )
    manifest = load_json(manifest_path)
    if manifest.get("manifest_version") != fixture_config.get("manifest_version"):
        raise RunnerError("Coding fixture manifest version mismatch")
    manifest_files = manifest.get("files")
    if not isinstance(manifest_files, list) or not manifest_files:
        raise RunnerError("Coding fixture manifest must define files")

    declared: dict[str, dict[str, Any]] = {}
    for entry in manifest_files:
        if not isinstance(entry, dict):
            raise RunnerError("Every fixture manifest entry must be an object")
        relative = _relative_posix_path(entry.get("path"), "fixture manifest")
        if relative in declared:
            raise RunnerError(f"Duplicate fixture manifest path: {relative}")
        if not isinstance(entry.get("sha256"), str) or not re.fullmatch(
            r"[0-9a-f]{64}", entry["sha256"]
        ):
            raise RunnerError(f"Invalid fixture hash for {relative}")
        if not isinstance(entry.get("size_bytes"), int) or entry["size_bytes"] < 0:
            raise RunnerError(f"Invalid fixture size for {relative}")
        if not isinstance(entry.get("candidate_visible"), bool) or not isinstance(
            entry.get("protected"), bool
        ):
            raise RunnerError(f"Fixture flags must be boolean for {relative}")
        declared[relative] = entry

    actual = _fixture_inventory(fixture_root)
    if set(actual) != set(declared):
        missing = sorted(set(declared) - set(actual))
        undeclared = sorted(set(actual) - set(declared))
        raise RunnerError(
            f"Fixture inventory mismatch; missing={missing}, undeclared={undeclared}"
        )
    for relative, entry in declared.items():
        if actual[relative]["sha256"] != entry["sha256"]:
            raise RunnerError(f"Fixture hash mismatch for {relative}")
        if actual[relative]["size_bytes"] != entry["size_bytes"]:
            raise RunnerError(f"Fixture size mismatch for {relative}")

    context_files = candidate_context.get("files")
    if not isinstance(context_files, list) or not context_files:
        raise RunnerError("candidate_context.files must be a non-empty list")
    normalized_context = [
        _relative_posix_path(path, "candidate context") for path in context_files
    ]
    if len(set(normalized_context)) != len(normalized_context):
        raise RunnerError("candidate_context.files contains duplicates")
    expected_visible = {
        path for path, entry in declared.items() if entry["candidate_visible"]
    }
    if set(normalized_context) != expected_visible:
        raise RunnerError(
            "Candidate context must equal the manifest's candidate-visible files"
        )
    if candidate_context.get("tools_allowed") is not False:
        raise RunnerError("Track A candidate tools must be disabled")
    if candidate_context.get("browsing_allowed") is not False:
        raise RunnerError("Track A candidate browsing must be disabled")

    allowed_globs = artifact_contract.get("allowed_path_globs")
    protected_globs = artifact_contract.get("protected_path_globs")
    if not isinstance(allowed_globs, list) or not all(
        isinstance(item, str) and item for item in allowed_globs
    ):
        raise RunnerError("patch_contract.allowed_path_globs must be strings")
    if not isinstance(protected_globs, list) or not all(
        isinstance(item, str) and item for item in protected_globs
    ):
        raise RunnerError("patch_contract.protected_path_globs must be strings")
    for relative, entry in declared.items():
        if entry["protected"] and _matches_any(relative, allowed_globs):
            raise RunnerError(f"Protected fixture path is also writable: {relative}")

    task_path = resolve_repo_path(repo_root, case["task_path"])
    system_path = resolve_repo_path(repo_root, prompt.get("system_path", ""))
    card_path = resolve_repo_path(
        repo_root, evaluation.get("benchmark_card_path", "")
    )
    hidden_test_path = resolve_repo_path(
        repo_root, verification.get("hidden_test_path", "")
    )
    for path, name in (
        (task_path, "task"),
        (system_path, "system prompt"),
        (card_path, "benchmark card"),
        (hidden_test_path, "hidden test"),
    ):
        if not path.is_file():
            raise RunnerError(f"Coding {name} does not exist: {path}")

    card = load_json(card_path)
    if card.get("case_id") != case["case_id"]:
        raise RunnerError("Coding benchmark card case_id mismatch")
    if card.get("case_version") != case["case_version"]:
        raise RunnerError("Coding benchmark card case_version mismatch")
    if card.get("card_version") != evaluation.get("benchmark_card_version"):
        raise RunnerError("Coding benchmark card version mismatch")
    if card.get("primary_outcome", {}).get("quality_scale_maximum") is not None:
        raise RunnerError("Track A primary outcome must not define a composite scale")

    maximum_bytes = artifact_contract.get("maximum_bytes")
    if (
        isinstance(maximum_bytes, bool)
        or not isinstance(maximum_bytes, int)
        or maximum_bytes < 1
    ):
        raise RunnerError("Coding artifact maximum_bytes must be positive")
    if artifact_contract["format"] == "whole_file_envelope":
        if (
            artifact_contract.get("opening_marker_template")
            != '<<<FILE path="{relative_path}">>>'
            or artifact_contract.get("closing_marker") != "<<<END FILE>>>"
        ):
            raise RunnerError("Unsupported whole-file envelope markers")
        if artifact_contract.get("canonical_final_newline") is not True:
            raise RunnerError("Whole-file artifacts must declare a final newline")
        minimum_files = artifact_contract.get("minimum_files")
        maximum_files = artifact_contract.get("maximum_files")
        if (
            isinstance(minimum_files, bool)
            or not isinstance(minimum_files, int)
            or minimum_files < 1
        ):
            raise RunnerError("whole_file_envelope minimum_files must be positive")
        if (
            isinstance(maximum_files, bool)
            or not isinstance(maximum_files, int)
            or maximum_files < minimum_files
        ):
            raise RunnerError(
                "whole_file_envelope maximum_files must be at least minimum_files"
            )
        if artifact_contract.get("existing_files_only") is not True:
            raise RunnerError("Track A whole-file contracts must replace existing files")
    test_timeout = verification.get("test_timeout_seconds")
    if not isinstance(test_timeout, (int, float)) or test_timeout <= 0:
        raise RunnerError("verification.test_timeout_seconds must be positive")
    known_command_tokens = {"{python}", "{fixture}", "{hidden_test}"}

    def validate_command(value: Any, context: str) -> list[str]:
        if not isinstance(value, list) or not value or not all(
            isinstance(item, str) and item for item in value
        ):
            raise RunnerError(f"{context} must be a non-empty list of strings")
        unknown_tokens = sorted(
            item
            for item in value
            if item.startswith("{")
            and item.endswith("}")
            and item not in known_command_tokens
        )
        if unknown_tokens:
            raise RunnerError(f"{context} uses unknown tokens: {unknown_tokens}")
        return value

    validate_command(
        verification.get("public_test_command"),
        "verification.public_test_command",
    )
    hidden_command = verification.get("hidden_test_command")
    if hidden_command is not None:
        validate_command(hidden_command, "verification.hidden_test_command")
        if "{hidden_test}" not in hidden_command or "{fixture}" not in hidden_command:
            raise RunnerError(
                "verification.hidden_test_command must use {hidden_test} and {fixture}"
            )
    runtime_command = verification.get("runtime_version_command")
    if runtime_command is not None:
        validate_command(
            runtime_command,
            "verification.runtime_version_command",
        )

    for key in ("num_ctx", "num_predict"):
        value = inference_defaults.get(key)
        if isinstance(value, bool) or not isinstance(value, int) or value < 1:
            raise RunnerError(f"inference_defaults.{key} must be a positive integer")
    temperature = inference_defaults.get("temperature")
    if isinstance(temperature, bool) or not isinstance(temperature, (int, float)):
        raise RunnerError("inference_defaults.temperature must be numeric")
    seed = inference_defaults.get("seed")
    if isinstance(seed, bool) or not isinstance(seed, int):
        raise RunnerError("inference_defaults.seed must be an integer")
    if not isinstance(inference_defaults.get("think"), (bool, str)):
        raise RunnerError("inference_defaults.think must be boolean or string")
    if not isinstance(inference_defaults.get("keep_alive"), str):
        raise RunnerError("inference_defaults.keep_alive must be a string")
    inference_timeout = inference_defaults.get("timeout_seconds")
    if (
        isinstance(inference_timeout, bool)
        or not isinstance(inference_timeout, (int, float))
        or inference_timeout <= 0
    ):
        raise RunnerError("inference_defaults.timeout_seconds must be positive")

    task_text = task_path.read_text(encoding="utf-8").strip()
    snapshot_parts = [task_text, "", "# Repository snapshot"]
    for relative in normalized_context:
        content = (fixture_root / relative).read_text(encoding="utf-8").rstrip()
        snapshot_parts.extend(
            ["", f"--- BEGIN FILE: {relative} ---", content, f"--- END FILE: {relative} ---"]
        )

    manifest_digest = sha256_text(
        json.dumps(manifest_files, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    )
    return {
        "case": case,
        "case_path": resolved_case_path,
        "card": card,
        "card_path": card_path,
        "fixture_root": fixture_root,
        "manifest": manifest,
        "manifest_path": manifest_path,
        "manifest_sha256": manifest_digest,
        "artifact_contract": artifact_contract,
        "baseline_inventory": actual,
        "protected_paths": {
            path for path, entry in declared.items() if entry["protected"]
        },
        "task_path": task_path,
        "task_sha256": sha256_file(task_path),
        "hidden_test_path": hidden_test_path,
        "hidden_test_sha256": sha256_file(hidden_test_path),
        "system_message": system_path.read_text(encoding="utf-8").strip(),
        "user_message": "\n".join(snapshot_parts).strip(),
    }


def parse_candidate_patch(response_text: str, contract: dict[str, Any]) -> dict[str, Any]:
    """Normalize and validate the visible patch envelope and declared paths."""
    stripped = response_text.strip()
    if not stripped:
        return {
            "output_status": "empty",
            "failure_code": "empty_output",
            "patch_text": None,
            "paths": [],
            "outer_fence_removed": False,
        }
    if len(stripped.encode("utf-8")) > contract["maximum_bytes"]:
        return {
            "output_status": "malformed",
            "failure_code": "malformed_patch",
            "reason": "Patch exceeds maximum_bytes",
            "patch_text": None,
            "paths": [],
            "outer_fence_removed": False,
        }

    outer_fence_removed = False
    if stripped.startswith("```diff\n") and stripped.endswith("\n```"):
        if not contract.get("single_outer_diff_fence_allowed", False):
            return {
                "output_status": "malformed",
                "failure_code": "malformed_patch",
                "reason": "Outer diff fence is not allowed",
                "patch_text": None,
                "paths": [],
                "outer_fence_removed": False,
            }
        stripped = stripped[len("```diff\n") : -len("\n```")].strip()
        outer_fence_removed = True
    elif "```" in stripped:
        return {
            "output_status": "malformed",
            "failure_code": "malformed_patch",
            "reason": "Unexpected code fence or prose around patch",
            "patch_text": None,
            "paths": [],
            "outer_fence_removed": False,
        }

    unsupported_directives = (
        "GIT binary patch",
        "Binary files ",
        "rename from ",
        "rename to ",
        "old mode ",
        "new mode ",
        "new file mode 120000",
    )
    if any(
        line.startswith(unsupported_directives) for line in stripped.splitlines()
    ):
        return {
            "output_status": "malformed",
            "failure_code": "malformed_patch",
            "reason": "Binary patches, renames, mode changes and symlinks are unsupported",
            "patch_text": None,
            "paths": [],
            "outer_fence_removed": outer_fence_removed,
        }

    if not stripped.startswith("diff --git ") or "\n@@" not in stripped:
        return {
            "output_status": "malformed",
            "failure_code": "malformed_patch",
            "reason": "Expected a Git-style unified diff with at least one hunk",
            "patch_text": None,
            "paths": [],
            "outer_fence_removed": outer_fence_removed,
        }

    headers = re.findall(r"(?m)^diff --git a/([^\s]+) b/([^\s]+)$", stripped)
    if not headers:
        return {
            "output_status": "malformed",
            "failure_code": "malformed_patch",
            "reason": "No valid diff --git file header found",
            "patch_text": None,
            "paths": [],
            "outer_fence_removed": outer_fence_removed,
        }

    paths: list[str] = []
    for old_path, new_path in headers:
        try:
            old_normalized = _relative_posix_path(old_path, "patch header")
            new_normalized = _relative_posix_path(new_path, "patch header")
        except RunnerError as exc:
            return {
                "output_status": "malformed",
                "failure_code": "patch_scope_violation",
                "reason": str(exc),
                "patch_text": None,
                "paths": paths,
                "outer_fence_removed": outer_fence_removed,
            }
        if old_normalized != new_normalized:
            return {
                "output_status": "malformed",
                "failure_code": "patch_scope_violation",
                "reason": "Renames are outside the Track A patch contract",
                "patch_text": None,
                "paths": paths,
                "outer_fence_removed": outer_fence_removed,
            }
        paths.append(new_normalized)

    unique_paths = sorted(set(paths))
    allowed_globs = contract["allowed_path_globs"]
    if any(not _matches_any(path, allowed_globs) for path in unique_paths):
        return {
            "output_status": "malformed",
            "failure_code": "patch_scope_violation",
            "reason": "Patch header contains a path outside allowed_path_globs",
            "patch_text": None,
            "paths": unique_paths,
            "outer_fence_removed": outer_fence_removed,
        }

    return {
        "output_status": "valid",
        "failure_code": None,
        "artifact_format": "git_unified_diff",
        "patch_text": stripped + "\n",
        "paths": unique_paths,
        "outer_fence_removed": outer_fence_removed,
    }


def parse_candidate_files(response_text: str, contract: dict[str, Any]) -> dict[str, Any]:
    """Parse a strict sequence of complete-file replacement envelopes."""
    stripped = response_text.strip()
    empty_result = {
        "output_status": "empty",
        "failure_code": "empty_output",
        "artifact_format": "whole_file_envelope",
        "files": [],
        "paths": [],
    }
    if not stripped:
        return empty_result
    if len(stripped.encode("utf-8")) > contract["maximum_bytes"]:
        return {
            **empty_result,
            "output_status": "malformed",
            "failure_code": "malformed_artifact",
            "reason": "Whole-file response exceeds maximum_bytes",
        }

    header_pattern = re.compile(r'<<<FILE path="([^"\r\n]+)">>>\n')
    end_marker = "\n<<<END FILE>>>"
    position = 0
    files: list[dict[str, Any]] = []
    seen_paths: set[str] = set()
    while position < len(stripped):
        header = header_pattern.match(stripped, position)
        if header is None:
            return {
                **empty_result,
                "output_status": "malformed",
                "failure_code": "malformed_artifact",
                "reason": "Expected a whole-file opening marker with no prose",
                "files": files,
                "paths": sorted(seen_paths),
            }
        try:
            path = _relative_posix_path(header.group(1), "whole-file header")
        except RunnerError as exc:
            return {
                **empty_result,
                "output_status": "malformed",
                "failure_code": "artifact_scope_violation",
                "reason": str(exc),
                "files": files,
                "paths": sorted(seen_paths),
            }
        if path in seen_paths:
            return {
                **empty_result,
                "output_status": "malformed",
                "failure_code": "malformed_artifact",
                "reason": f"Duplicate whole-file path: {path}",
                "files": files,
                "paths": sorted(seen_paths),
            }
        if not _matches_any(path, contract["allowed_path_globs"]):
            return {
                **empty_result,
                "output_status": "malformed",
                "failure_code": "artifact_scope_violation",
                "reason": f"Whole-file path is outside allowed_path_globs: {path}",
                "files": files,
                "paths": sorted(seen_paths | {path}),
            }

        content_start = header.end()
        content_end = stripped.find(end_marker, content_start)
        if content_end < 0:
            return {
                **empty_result,
                "output_status": "malformed",
                "failure_code": "malformed_artifact",
                "reason": f"Missing whole-file closing marker for {path}",
                "files": files,
                "paths": sorted(seen_paths | {path}),
            }
        content = stripped[content_start:content_end]
        if not content:
            return {
                **empty_result,
                "output_status": "malformed",
                "failure_code": "malformed_artifact",
                "reason": f"Whole-file content is empty for {path}",
                "files": files,
                "paths": sorted(seen_paths | {path}),
            }
        canonical_content = content + "\n"
        files.append(
            {
                "path": path,
                "content": canonical_content,
                "sha256": sha256_text(canonical_content),
                "size_bytes": len(canonical_content.encode("utf-8")),
            }
        )
        seen_paths.add(path)
        position = content_end + len(end_marker)
        if position == len(stripped):
            break
        if not stripped.startswith("\n<<<FILE ", position):
            return {
                **empty_result,
                "output_status": "malformed",
                "failure_code": "malformed_artifact",
                "reason": "Expected the next file marker with no intervening prose",
                "files": files,
                "paths": sorted(seen_paths),
            }
        position += 1

    if not contract["minimum_files"] <= len(files) <= contract["maximum_files"]:
        return {
            **empty_result,
            "output_status": "malformed",
            "failure_code": "malformed_artifact",
            "reason": (
                "Whole-file response contains an unsupported number of files: "
                f"{len(files)}"
            ),
            "files": files,
            "paths": sorted(seen_paths),
        }
    return {
        "output_status": "valid",
        "failure_code": None,
        "artifact_format": "whole_file_envelope",
        "files": files,
        "paths": sorted(seen_paths),
    }


def parse_candidate_artifact(
    response_text: str, contract: dict[str, Any]
) -> dict[str, Any]:
    """Parse one candidate response according to its versioned artifact format."""
    if contract["format"] == "git_unified_diff":
        return parse_candidate_patch(response_text, contract)
    if contract["format"] == "whole_file_envelope":
        return parse_candidate_files(response_text, contract)
    raise RunnerError(f"Unsupported coding artifact format: {contract['format']!r}")


def _run_process(
    command: list[str],
    *,
    cwd: Path,
    timeout_seconds: float,
    env: dict[str, str] | None = None,
    input_text: str | None = None,
) -> dict[str, Any]:
    def output_text(value: str | bytes | None) -> str:
        if isinstance(value, bytes):
            return value.decode("utf-8", errors="replace")
        return value or ""

    started = time.perf_counter()
    try:
        result = subprocess.run(
            command,
            cwd=cwd,
            env=env,
            input=input_text,
            capture_output=True,
            text=True,
            timeout=timeout_seconds,
            check=False,
        )
    except subprocess.TimeoutExpired as exc:
        return {
            "status": "timeout",
            "passed": False,
            "exit_code": None,
            "wall_time_seconds": time.perf_counter() - started,
            "stdout": output_text(exc.stdout),
            "stderr": output_text(exc.stderr),
        }
    except OSError as exc:
        return {
            "status": "error",
            "passed": False,
            "exit_code": None,
            "wall_time_seconds": time.perf_counter() - started,
            "stdout": "",
            "stderr": str(exc),
        }
    return {
        "status": "complete",
        "passed": result.returncode == 0,
        "exit_code": result.returncode,
        "wall_time_seconds": time.perf_counter() - started,
        "stdout": result.stdout,
        "stderr": result.stderr,
    }


def _test_environment(workspace: Path) -> dict[str, str]:
    environment = os.environ.copy()
    environment["PYTHONPATH"] = str(workspace / "src")
    environment["PYTHONDONTWRITEBYTECODE"] = "1"
    return environment


def _render_verifier_command(
    command: list[str], loaded: dict[str, Any], workspace: Path
) -> list[str]:
    replacements = {
        "{python}": sys.executable,
        "{fixture}": str(workspace),
        "{hidden_test}": str(loaded["hidden_test_path"]),
    }
    return [replacements.get(item, item) for item in command]


def _run_verifier_tests(
    loaded: dict[str, Any], workspace: Path
) -> dict[str, Any]:
    verification = loaded["case"]["verification"]
    timeout_seconds = float(verification["test_timeout_seconds"])
    public_command = _render_verifier_command(
        verification["public_test_command"], loaded, workspace
    )
    hidden_command = _render_verifier_command(
        verification.get(
            "hidden_test_command",
            ["{python}", "{hidden_test}", "{fixture}"],
        ),
        loaded,
        workspace,
    )
    environment = _test_environment(workspace)
    runtime = None
    if verification.get("runtime_version_command") is not None:
        runtime = _run_process(
            _render_verifier_command(
                verification["runtime_version_command"], loaded, workspace
            ),
            cwd=workspace,
            timeout_seconds=min(timeout_seconds, 10),
            env=environment,
        )
    public = _run_process(
        public_command,
        cwd=workspace,
        timeout_seconds=timeout_seconds,
        env=environment,
    )
    hidden = _run_process(
        hidden_command,
        cwd=workspace,
        timeout_seconds=timeout_seconds,
        env=environment,
    )
    return {"runtime": runtime, "public": public, "hidden": hidden}


def run_public_tests_in_workspace(
    repo_root: Path,
    case_path: Path,
    workspace: Path,
) -> dict[str, Any]:
    """Run only candidate-visible verification for an agent workspace."""
    loaded = load_coding_case(repo_root, case_path)
    if not workspace.is_dir() or workspace.is_symlink():
        raise RunnerError(f"Agent workspace is not a regular directory: {workspace}")

    integrity = _workspace_integrity(loaded, workspace)
    if not integrity["passed"]:
        return {
            "case_id": loaded["case"]["case_id"],
            "case_version": loaded["case"]["case_version"],
            "status": "rejected",
            "passed": False,
            "failure_code": "workspace_scope_violation",
            "integrity": integrity,
            "runtime": None,
            "public": None,
            "hidden_tests_executed": False,
        }

    verification = loaded["case"]["verification"]
    timeout_seconds = float(verification["test_timeout_seconds"])
    environment = _test_environment(workspace)
    runtime = None
    if verification.get("runtime_version_command") is not None:
        runtime = _run_process(
            _render_verifier_command(
                verification["runtime_version_command"], loaded, workspace
            ),
            cwd=workspace,
            timeout_seconds=min(timeout_seconds, 10),
            env=environment,
        )
    public = _run_process(
        _render_verifier_command(
            verification["public_test_command"], loaded, workspace
        ),
        cwd=workspace,
        timeout_seconds=timeout_seconds,
        env=environment,
    )
    runtime_ready = runtime is None or runtime["passed"]
    passed = runtime_ready and public["passed"]
    failure_code = None
    if not runtime_ready:
        failure_code = "verification_runtime_failure"
    elif public["status"] == "timeout":
        failure_code = "verification_timeout"
    elif not public["passed"]:
        failure_code = "public_tests_failed"
    return {
        "case_id": loaded["case"]["case_id"],
        "case_version": loaded["case"]["case_version"],
        "status": "complete",
        "passed": passed,
        "failure_code": failure_code,
        "integrity": integrity,
        "runtime": runtime,
        "public": public,
        "hidden_tests_executed": False,
    }


def verify_coding_workspace(
    repo_root: Path,
    case_path: Path,
    workspace: Path,
) -> dict[str, Any]:
    """Run final public and hidden verification on an agent workspace."""
    loaded = load_coding_case(repo_root, case_path)
    if not workspace.is_dir() or workspace.is_symlink():
        raise RunnerError(f"Agent workspace is not a regular directory: {workspace}")

    integrity = _workspace_integrity(loaded, workspace)
    base = {
        "case_id": loaded["case"]["case_id"],
        "case_version": loaded["case"]["case_version"],
        "verifier_version": loaded["case"]["verification"]["version"],
        "fixture_manifest_sha256": loaded["manifest_sha256"],
        "hidden_test_sha256": loaded["hidden_test_sha256"],
        "integrity": integrity,
        "verification_status": "failed",
        "verified_success": False,
    }
    if not integrity["passed"]:
        return {
            **base,
            "failure_code": "workspace_scope_violation",
            "tests": None,
        }

    tests = _run_verifier_tests(loaded, workspace)
    failure_code = None
    if tests["runtime"] is not None and not tests["runtime"]["passed"]:
        failure_code = "verification_runtime_failure"
    elif tests["public"]["status"] == "timeout" or tests["hidden"]["status"] == "timeout":
        failure_code = "verification_timeout"
    elif not tests["public"]["passed"]:
        failure_code = "public_tests_failed"
    elif not tests["hidden"]["passed"]:
        failure_code = "hidden_tests_failed"
    verified_success = failure_code is None
    return {
        **base,
        "verification_status": "passed" if verified_success else "failed",
        "verified_success": verified_success,
        "failure_code": failure_code,
        "tests": tests,
    }


def audit_coding_case(repo_root: Path, case_path: Path) -> dict[str, Any]:
    """Verify fixture integrity and confirm the frozen baseline is red."""
    loaded = load_coding_case(repo_root, case_path)
    with tempfile.TemporaryDirectory(prefix="llm-benchmark-coding-audit-") as temp:
        workspace = Path(temp) / "fixture"
        shutil.copytree(loaded["fixture_root"], workspace)
        tests = _run_verifier_tests(loaded, workspace)
    expected = loaded["case"]["verification"]["baseline_expected"]
    runtime_ready = tests["runtime"] is None or tests["runtime"]["passed"]
    expectations_met = (
        runtime_ready
        and tests["public"]["passed"] is expected["public_tests_pass"]
        and tests["hidden"]["passed"] is expected["hidden_tests_pass"]
    )
    return {
        "case_id": loaded["case"]["case_id"],
        "case_version": loaded["case"]["case_version"],
        "artifact_format": loaded["artifact_contract"]["format"],
        "fixture_manifest_sha256": loaded["manifest_sha256"],
        "task_sha256": loaded["task_sha256"],
        "hidden_test_sha256": loaded["hidden_test_sha256"],
        "public_tests_pass": tests["public"]["passed"],
        "hidden_tests_pass": tests["hidden"]["passed"],
        "verification_runtime": tests["runtime"],
        "baseline_expectations_met": expectations_met,
        "status": "complete" if expectations_met else "failed",
    }


def _workspace_integrity(
    loaded: dict[str, Any], workspace: Path
) -> dict[str, Any]:
    current = _fixture_inventory(workspace)
    baseline = loaded["baseline_inventory"]
    changed_paths = sorted(
        path
        for path in set(baseline) | set(current)
        if baseline.get(path) != current.get(path)
    )
    contract = loaded["artifact_contract"]
    allowed_globs = contract["allowed_path_globs"]
    protected_globs = contract["protected_path_globs"]
    scope_violations = sorted(
        path for path in changed_paths if not _matches_any(path, allowed_globs)
    )
    protected_changes = sorted(
        path
        for path in changed_paths
        if _matches_any(path, protected_globs) or path in loaded["protected_paths"]
    )
    new_paths = sorted(set(current) - set(baseline))
    deleted_paths = sorted(set(baseline) - set(current))
    structure_violations = (
        sorted(set(new_paths) | set(deleted_paths))
        if contract.get("existing_files_only", False)
        else []
    )
    return {
        "changed_paths": changed_paths,
        "scope_violations": scope_violations,
        "protected_changes": protected_changes,
        "new_paths": new_paths,
        "deleted_paths": deleted_paths,
        "structure_violations": structure_violations,
        "passed": (
            not scope_violations
            and not protected_changes
            and not structure_violations
        ),
    }


def verify_candidate_artifact(
    repo_root: Path,
    case_path: Path,
    response_text: str,
) -> dict[str, Any]:
    """Install one candidate artifact in isolation and run all verifier layers."""
    loaded = load_coding_case(repo_root, case_path)
    contract = loaded["artifact_contract"]
    parsed = parse_candidate_artifact(response_text, contract)
    artifact_format = contract["format"]
    artifact_sha256 = None
    if parsed["output_status"] == "valid":
        artifact_sha256 = (
            sha256_text(parsed["patch_text"])
            if artifact_format == "git_unified_diff"
            else sha256_text(response_text.strip())
        )
    base_result: dict[str, Any] = {
        "case_id": loaded["case"]["case_id"],
        "case_version": loaded["case"]["case_version"],
        "verifier_version": loaded["case"]["verification"]["version"],
        "output_status": parsed["output_status"],
        "verification_status": "unavailable",
        "task_status": "failed",
        "verified_success": False,
        "failure_code": parsed.get("failure_code"),
        "artifact": {
            "format": artifact_format,
            "paths": parsed.get("paths", []),
            "sha256": artifact_sha256,
            "files": [
                {
                    "path": item["path"],
                    "sha256": item["sha256"],
                    "size_bytes": item["size_bytes"],
                }
                for item in parsed.get("files", [])
            ],
        },
        "fixture_manifest_sha256": loaded["manifest_sha256"],
        "hidden_test_sha256": loaded["hidden_test_sha256"],
    }
    if artifact_format == "git_unified_diff":
        base_result["patch"] = {
            "paths": parsed.get("paths", []),
            "outer_fence_removed": parsed.get("outer_fence_removed", False),
            "sha256": artifact_sha256,
        }
    if parsed["output_status"] != "valid":
        if parsed.get("reason"):
            base_result["failure_reason"] = parsed["reason"]
        return base_result

    application_records: dict[str, Any] = {}
    with tempfile.TemporaryDirectory(prefix="llm-benchmark-coding-verify-") as temp:
        workspace = Path(temp) / "fixture"
        shutil.copytree(loaded["fixture_root"], workspace)

        if artifact_format == "git_unified_diff":
            apply_check = _run_process(
                ["git", "apply", "--no-index", "--check", "-"],
                cwd=workspace,
                timeout_seconds=10,
                input_text=parsed["patch_text"],
            )
            application_records["patch_apply_check"] = apply_check
            if not apply_check["passed"]:
                base_result.update(
                    {
                        "verification_status": "failed",
                        "failure_code": (
                            "verification_timeout"
                            if apply_check["status"] == "timeout"
                            else "patch_apply_failure"
                        ),
                        **application_records,
                    }
                )
                return base_result

            apply_result = _run_process(
                ["git", "apply", "--no-index", "--whitespace=nowarn", "-"],
                cwd=workspace,
                timeout_seconds=10,
                input_text=parsed["patch_text"],
            )
            application_records["patch_apply"] = apply_result
            if not apply_result["passed"]:
                base_result.update(
                    {
                        "verification_status": "failed",
                        "failure_code": (
                            "verification_timeout"
                            if apply_result["status"] == "timeout"
                            else "patch_apply_failure"
                        ),
                        **application_records,
                    }
                )
                return base_result
        else:
            missing_paths = sorted(
                item["path"]
                for item in parsed["files"]
                if item["path"] not in loaded["baseline_inventory"]
            )
            if missing_paths:
                base_result.update(
                    {
                        "verification_status": "failed",
                        "failure_code": "artifact_scope_violation",
                        "artifact_install": {
                            "status": "rejected",
                            "passed": False,
                            "missing_paths": missing_paths,
                        },
                    }
                )
                return base_result
            try:
                for item in parsed["files"]:
                    destination = workspace.joinpath(*PurePosixPath(item["path"]).parts)
                    if destination.is_symlink() or not destination.is_file():
                        raise OSError(f"Replacement target is not a regular file: {item['path']}")
                    destination.write_text(item["content"], encoding="utf-8")
            except OSError as exc:
                base_result.update(
                    {
                        "verification_status": "failed",
                        "failure_code": "artifact_install_failure",
                        "artifact_install": {
                            "status": "error",
                            "passed": False,
                            "error": str(exc),
                        },
                    }
                )
                return base_result
            application_records["artifact_install"] = {
                "status": "complete",
                "passed": True,
                "paths": parsed["paths"],
                "canonical_final_newline_enforced": True,
            }

        integrity = _workspace_integrity(loaded, workspace)
        if not integrity["passed"]:
            base_result.update(
                {
                    "verification_status": "failed",
                    "failure_code": (
                        "protected_file_modified"
                        if integrity["protected_changes"]
                        else (
                            "patch_scope_violation"
                            if artifact_format == "git_unified_diff"
                            else "artifact_scope_violation"
                        )
                    ),
                    **application_records,
                    "integrity": integrity,
                }
            )
            return base_result

        tests = _run_verifier_tests(loaded, workspace)

    failure_code = None
    if tests["runtime"] is not None and not tests["runtime"]["passed"]:
        failure_code = "verification_runtime_failure"
    elif tests["public"]["status"] == "timeout" or tests["hidden"]["status"] == "timeout":
        failure_code = "verification_timeout"
    elif not tests["public"]["passed"]:
        failure_code = "public_tests_failed"
    elif not tests["hidden"]["passed"]:
        failure_code = "hidden_tests_failed"
    verified_success = failure_code is None
    base_result.update(
        {
            "verification_status": "passed" if verified_success else "failed",
            "task_status": "verified_success" if verified_success else "failed",
            "verified_success": verified_success,
            "failure_code": failure_code,
            **application_records,
            "integrity": integrity,
            "tests": tests,
        }
    )
    return base_result


def verify_candidate_patch(
    repo_root: Path,
    case_path: Path,
    response_text: str,
) -> dict[str, Any]:
    """Backward-compatible alias for the versioned artifact verifier."""
    return verify_candidate_artifact(repo_root, case_path, response_text)


def diagnose_fenced_file_transport(
    repo_root: Path,
    case_path: Path,
    protocol_path: Path,
    response_text: str,
) -> dict[str, Any]:
    """Verify code semantics after a preregistered fence-only normalization."""
    loaded = load_coding_case(repo_root, case_path)
    contract = loaded["artifact_contract"]
    if contract["format"] != "whole_file_envelope":
        raise RunnerError("Fenced-file diagnostics require a whole-file case")

    resolved_protocol_path = resolve_repo_path(repo_root, protocol_path)
    protocol = load_json(resolved_protocol_path)
    if protocol.get("schema_version") != "1.0.0":
        raise RunnerError("Unsupported transport diagnostic schema version")
    if protocol.get("status") != "frozen_before_comparison_execution":
        raise RunnerError("Transport diagnostic protocol is not frozen")
    if protocol.get("case_id") != loaded["case"]["case_id"]:
        raise RunnerError("Transport diagnostic case_id mismatch")
    if protocol.get("case_version") != loaded["case"]["case_version"]:
        raise RunnerError("Transport diagnostic case_version mismatch")

    strict = parse_candidate_artifact(response_text, contract)
    base_result: dict[str, Any] = {
        "schema_version": "1.0.0",
        "protocol_id": protocol.get("protocol_id"),
        "protocol_sha256": sha256_file(resolved_protocol_path),
        "case_id": loaded["case"]["case_id"],
        "case_version": loaded["case"]["case_version"],
        "source_response_sha256": sha256_text(response_text),
        "strict_output_status": strict["output_status"],
        "strict_failure_code": strict.get("failure_code"),
        "changes_primary_outcome": False,
        "new_inference_attempts": 0,
        "diagnostic_status": "not_eligible",
        "diagnostic_reason": None,
        "code_byte_identity_verified": False,
        "files": [],
        "normalized_artifact_sha256": None,
        "verification": None,
    }

    applicability = protocol.get("applicability")
    if not isinstance(applicability, dict):
        raise RunnerError("Transport diagnostic protocol lacks applicability")
    if strict["output_status"] not in applicability.get(
        "strict_output_statuses", []
    ) or strict.get("failure_code") not in applicability.get(
        "strict_failure_codes", []
    ):
        base_result["diagnostic_reason"] = (
            "Strict outcome is outside the frozen diagnostic applicability"
        )
        return base_result

    mappings = protocol.get("class_path_mappings")
    if not isinstance(mappings, list) or not mappings:
        raise RunnerError("Transport diagnostic protocol lacks class mappings")
    class_to_path: dict[str, str] = {}
    for item in mappings:
        if not isinstance(item, dict):
            raise RunnerError("Every diagnostic class mapping must be an object")
        class_name = item.get("class_name")
        path = item.get("path")
        if not isinstance(class_name, str) or not re.fullmatch(
            r"[A-Za-z_][A-Za-z0-9_]*", class_name
        ):
            raise RunnerError("Invalid diagnostic PHP class name")
        normalized_path = _relative_posix_path(path, "diagnostic class mapping")
        if class_name in class_to_path or normalized_path in class_to_path.values():
            raise RunnerError("Duplicate diagnostic class or path mapping")
        if not _matches_any(normalized_path, contract["allowed_path_globs"]):
            raise RunnerError("Diagnostic mapping is outside allowed paths")
        class_to_path[class_name] = normalized_path

    fence_pattern = re.compile(r"```php\n(.*?)\n```", re.DOTALL)
    matches = list(fence_pattern.finditer(response_text))
    minimum_files = applicability.get("minimum_files")
    maximum_files = applicability.get("maximum_files")
    if not isinstance(minimum_files, int) or not isinstance(maximum_files, int):
        raise RunnerError("Diagnostic file-count bounds must be integers")
    if not minimum_files <= len(matches) <= maximum_files:
        base_result["diagnostic_reason"] = (
            "PHP fence count is outside the frozen diagnostic bounds"
        )
        return base_result

    gaps = [response_text[: matches[0].start()]]
    gaps.extend(
        response_text[left.end() : right.start()]
        for left, right in zip(matches, matches[1:])
    )
    gaps.append(response_text[matches[-1].end() :])
    if any(gap.strip() for gap in gaps):
        base_result["diagnostic_reason"] = (
            "Response contains content outside the PHP fences"
        )
        return base_result

    normalized_parts: list[str] = []
    seen_paths: set[str] = set()
    source_files: list[dict[str, Any]] = []
    for match in matches:
        code = match.group(1) + "\n"
        declared_classes = [
            class_name
            for class_name in class_to_path
            if re.search(
                rf"\b(?:final\s+)?(?:readonly\s+)?class\s+{re.escape(class_name)}\b",
                code,
            )
        ]
        if len(declared_classes) != 1:
            base_result["diagnostic_reason"] = (
                "A PHP fence does not declare exactly one mapped class"
            )
            return base_result
        class_name = declared_classes[0]
        path = class_to_path[class_name]
        if path in seen_paths:
            base_result["diagnostic_reason"] = "Duplicate mapped PHP class"
            return base_result
        if not code.startswith("<?php\n"):
            base_result["diagnostic_reason"] = (
                "A mapped PHP fence does not start with a PHP opening tag"
            )
            return base_result
        seen_paths.add(path)
        source_hash = sha256_text(code)
        source_files.append(
            {
                "class_name": class_name,
                "path": path,
                "source_code_sha256": source_hash,
                "normalized_code_sha256": source_hash,
                "size_bytes": len(code.encode("utf-8")),
            }
        )
        normalized_parts.append(
            f'<<<FILE path="{path}">>>\n{code}<<<END FILE>>>'
        )

    normalized_response = "\n".join(normalized_parts)
    normalized = parse_candidate_files(normalized_response, contract)
    if normalized["output_status"] != "valid":
        base_result["diagnostic_reason"] = (
            "Normalized response does not satisfy the strict whole-file parser"
        )
        return base_result
    normalized_hashes = {
        item["path"]: item["sha256"] for item in normalized["files"]
    }
    identity_verified = all(
        item["source_code_sha256"] == normalized_hashes.get(item["path"])
        for item in source_files
    )
    if not identity_verified:
        raise RunnerError("Transport normalization changed candidate code bytes")

    verification = verify_candidate_artifact(
        repo_root,
        case_path,
        normalized_response,
    )
    base_result.update(
        {
            "diagnostic_status": "complete",
            "diagnostic_reason": None,
            "code_byte_identity_verified": True,
            "files": source_files,
            "normalized_artifact_sha256": verification["artifact"]["sha256"],
            "verification": verification,
        }
    )
    return base_result


def _pending_verification_record(
    loaded: dict[str, Any], parsed: dict[str, Any], response_text: str
) -> dict[str, Any]:
    """Describe a generated artifact whose executable checks are deferred."""
    contract = loaded["artifact_contract"]
    artifact_sha256 = (
        sha256_text(parsed["patch_text"])
        if parsed.get("patch_text") is not None
        else (
            sha256_text(response_text.strip())
            if parsed["output_status"] == "valid"
            else None
        )
    )
    return {
        "case_id": loaded["case"]["case_id"],
        "case_version": loaded["case"]["case_version"],
        "verifier_version": loaded["case"]["verification"]["version"],
        "output_status": parsed["output_status"],
        "verification_status": "pending",
        "task_status": "pending",
        "verified_success": None,
        "failure_code": parsed.get("failure_code"),
        "artifact": {
            "format": contract["format"],
            "paths": parsed.get("paths", []),
            "sha256": artifact_sha256,
            "files": [
                {
                    "path": item["path"],
                    "sha256": item["sha256"],
                    "size_bytes": item["size_bytes"],
                }
                for item in parsed.get("files", [])
            ],
        },
        "fixture_manifest_sha256": loaded["manifest_sha256"],
        "hidden_test_sha256": loaded["hidden_test_sha256"],
    }


def _resolved_inference_options(
    config: CodingRunConfig, case: dict[str, Any]
) -> dict[str, Any]:
    defaults = case["inference_defaults"]
    return {
        "temperature": (
            config.temperature
            if config.temperature is not None
            else defaults["temperature"]
        ),
        "seed": config.seed if config.seed is not None else defaults["seed"],
        "num_ctx": config.num_ctx if config.num_ctx is not None else defaults["num_ctx"],
        "num_predict": (
            config.num_predict
            if config.num_predict is not None
            else defaults["num_predict"]
        ),
        "think": config.think if config.think is not None else defaults["think"],
        "keep_alive": (
            config.keep_alive
            if config.keep_alive is not None
            else defaults["keep_alive"]
        ),
        "timeout_seconds": (
            config.timeout_seconds
            if config.timeout_seconds is not None
            else float(defaults["timeout_seconds"])
        ),
    }


def run_track_a_once(repo_root: Path, config: CodingRunConfig) -> dict[str, Any]:
    """Run one direct Ollama artifact attempt and verify the delivered outcome."""
    loaded = load_coding_case(repo_root, config.case_path)
    case = loaded["case"]
    resolved = _resolved_inference_options(config, case)
    client = OllamaClient(config.host, timeout_seconds=resolved["timeout_seconds"])
    version_response = client.version()
    model_tag = find_model(client.list_models(), config.model)
    model_show = client.show_model(config.model)

    timestamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    run_id = f"coding-run-{timestamp}-{secrets.token_hex(4)}"
    results_dir = resolve_repo_path(repo_root, config.results_dir)
    run_dir = results_dir / run_id
    run_dir.mkdir(parents=True, exist_ok=False)

    options = {
        "temperature": resolved["temperature"],
        "seed": resolved["seed"],
        "num_ctx": resolved["num_ctx"],
        "num_predict": resolved["num_predict"],
    }
    messages = [
        {"role": "system", "content": loaded["system_message"]},
        {"role": "user", "content": loaded["user_message"]},
    ]
    request_payload = {
        "model": config.model,
        "messages": messages,
        "stream": True,
        "think": resolved["think"],
        "keep_alive": resolved["keep_alive"],
        "options": options,
    }
    write_json(run_dir / "request.json", request_payload)
    write_json(run_dir / "ollama-show.json", model_show)

    started_at = utc_now()
    start_clock = time.perf_counter()
    first_content_seconds: float | None = None
    content_parts: list[str] = []
    thinking_parts: list[str] = []
    final_event: dict[str, Any] | None = None
    try:
        with (run_dir / "stream.ndjson").open("w", encoding="utf-8") as stream_file:
            for event in client.stream_chat(request_payload):
                stream_file.write(
                    json.dumps(event, ensure_ascii=False, separators=(",", ":"))
                    + "\n"
                )
                message = event.get("message") or {}
                content = message.get("content") or ""
                thinking = message.get("thinking") or ""
                if content and first_content_seconds is None:
                    first_content_seconds = time.perf_counter() - start_clock
                if content:
                    content_parts.append(content)
                if thinking:
                    thinking_parts.append(thinking)
                if event.get("done") is True:
                    final_event = event
    except Exception as exc:
        write_json(
            run_dir / "failure.json",
            {
                "schema_version": "1.0.0",
                "run_id": run_id,
                "status": "infrastructure_failed",
                "failure_code": "runtime_failure",
                "started_at": started_at,
                "failed_at": utc_now(),
                "model": config.model,
                "error_type": type(exc).__name__,
                "error": str(exc),
            },
        )
        raise

    wall_time_seconds = time.perf_counter() - start_clock
    if final_event is None:
        raise RunnerError("Ollama stream ended without a final done=true event")

    response_text = "".join(content_parts).strip()
    thinking_text = "".join(thinking_parts).strip()
    response_path = run_dir / "response.txt"
    response_path.write_text(response_text + "\n", encoding="utf-8")
    if thinking_text:
        (run_dir / "thinking.txt").write_text(thinking_text + "\n", encoding="utf-8")
    contract = loaded["artifact_contract"]
    parsed = parse_candidate_artifact(response_text, contract)
    if parsed.get("patch_text") is not None:
        (run_dir / "candidate.patch").write_text(
            parsed["patch_text"], encoding="utf-8"
        )
    candidate_files: list[str] = []
    if parsed["output_status"] == "valid" and parsed.get("files"):
        candidate_root = run_dir / "candidate-files"
        for item in parsed["files"]:
            candidate_path = candidate_root.joinpath(
                *PurePosixPath(item["path"]).parts
            )
            candidate_path.parent.mkdir(parents=True, exist_ok=True)
            candidate_path.write_text(item["content"], encoding="utf-8")
            candidate_files.append(item["path"])
        write_json(
            run_dir / "candidate-files.json",
            {
                "schema_version": "1.0.0",
                "format": "whole_file_envelope",
                "files": [
                    {
                        "path": item["path"],
                        "sha256": item["sha256"],
                        "size_bytes": item["size_bytes"],
                    }
                    for item in parsed["files"]
                ],
            },
        )

    verification = (
        _pending_verification_record(loaded, parsed, response_text)
        if config.defer_verification
        else verify_candidate_artifact(repo_root, config.case_path, response_text)
    )
    write_json(run_dir / "verification.json", verification)
    metrics = {
        "wall_time_seconds": wall_time_seconds,
        "time_to_first_content_seconds": first_content_seconds,
        "total_duration_seconds": nanoseconds_to_seconds(final_event.get("total_duration")),
        "load_duration_seconds": nanoseconds_to_seconds(final_event.get("load_duration")),
        "prompt_eval_count": final_event.get("prompt_eval_count"),
        "prompt_eval_duration_seconds": nanoseconds_to_seconds(
            final_event.get("prompt_eval_duration")
        ),
        "prompt_tokens_per_second": tokens_per_second(
            final_event.get("prompt_eval_count"), final_event.get("prompt_eval_duration")
        ),
        "eval_count": final_event.get("eval_count"),
        "eval_duration_seconds": nanoseconds_to_seconds(final_event.get("eval_duration")),
        "output_tokens_per_second": tokens_per_second(
            final_event.get("eval_count"), final_event.get("eval_duration")
        ),
    }
    model_record = {
        "requested_name": config.model,
        "resolved_name": model_tag.get("name") or model_tag.get("model"),
        "digest": model_tag.get("digest"),
        "size_bytes": model_tag.get("size"),
        "modified_at": model_tag.get("modified_at"),
        "details": model_tag.get("details"),
        "capabilities": model_show.get("capabilities"),
        "parameters": model_show.get("parameters"),
        "template_sha256": sha256_text(model_show.get("template", "")),
    }
    record = {
        "schema_version": "1.0.0",
        "run_id": run_id,
        "track": "A",
        "harness": {
            "name": (
                "local_llm_benchmark.direct_patch"
                if contract["format"] == "git_unified_diff"
                else "local_llm_benchmark.direct_files"
            ),
            "version": (
                "1.0.0"
                if contract["format"] == "git_unified_diff"
                else "1.1.0"
            ),
            "git_commit": git_commit(repo_root),
        },
        "started_at": started_at,
        "completed_at": utc_now(),
        "case": {
            "case_id": case["case_id"],
            "case_version": case["case_version"],
            "case_path": loaded["case_path"].relative_to(repo_root).as_posix(),
            "task_family": case["task_family"],
            "prompt_version": case["prompt"]["version"],
            "benchmark_card_version": case["evaluation"]["benchmark_card_version"],
            "artifact_contract_version": contract.get("version", "1.0.0"),
            "artifact_format": contract["format"],
            "fixture_manifest_sha256": loaded["manifest_sha256"],
            "task_sha256": loaded["task_sha256"],
            "verifier_version": case["verification"]["version"],
            "hidden_test_sha256": loaded["hidden_test_sha256"],
            "pre_run_task_features": loaded["card"]["pre_run_task_features"],
        },
        "deployment": {
            "ollama_host": client.host,
            "ollama_version": version_response.get("version"),
            "model": model_record,
            "options": options,
            "think": resolved["think"],
            "keep_alive": resolved["keep_alive"],
            "hardware": {
                "system": platform.system(),
                "release": platform.release(),
                "machine": platform.machine(),
                "processor": platform.processor() or None,
                "memory_total_bytes": memory_total_bytes(),
            },
        },
        "execution": {
            "execution_status": "completed",
            "endpoint": "/api/chat",
            "stream": True,
            "done_reason": final_event.get("done_reason"),
            "python_version": platform.python_version(),
        },
        "outcome": {
            "output_status": verification["output_status"],
            "verification_status": verification["verification_status"],
            "task_status": verification["task_status"],
            "verified_success": verification["verified_success"],
            "failure_code": verification["failure_code"],
        },
        "verification_execution": {
            "mode": "deferred" if config.defer_verification else "immediate",
            "completed_at": None if config.defer_verification else utc_now(),
            "runtime": (
                verification.get("tests", {}).get("runtime")
                if isinstance(verification.get("tests"), dict)
                else None
            ),
        },
        "metrics": metrics,
        "artifacts": {
            "request": "request.json",
            "raw_stream": "stream.ndjson",
            "response": "response.txt",
            "response_sha256": sha256_file(response_path),
            "thinking": "thinking.txt" if thinking_text else None,
            "candidate_patch": "candidate.patch" if parsed.get("patch_text") else None,
            "candidate_files": candidate_files or None,
            "candidate_files_manifest": (
                "candidate-files.json" if candidate_files else None
            ),
            "verification": "verification.json",
            "ollama_show": "ollama-show.json",
        },
    }
    write_json(run_dir / "run.json", record)
    return {
        "run_id": run_id,
        "run_dir": str(run_dir),
        "status": (
            "verification_pending" if config.defer_verification else "complete"
        ),
        "track": "A",
        "model": config.model,
        "case_id": case["case_id"],
        "done_reason": final_event.get("done_reason"),
        "verified_success": verification["verified_success"],
        "failure_code": verification["failure_code"],
        "metrics": metrics,
    }


def finalize_deferred_track_a_run(
    repo_root: Path, run_dir: Path
) -> dict[str, Any]:
    """Execute and persist verifier checks for one deferred Track A run."""
    resolved_run_dir = resolve_repo_path(repo_root, run_dir)
    if not resolved_run_dir.is_dir():
        raise RunnerError(f"Coding run directory does not exist: {resolved_run_dir}")
    run_path = resolved_run_dir / "run.json"
    record = load_json(run_path)
    if record.get("track") != "A":
        raise RunnerError("Only Track A runs can be finalized by this command")
    verification_execution = record.get("verification_execution")
    if not isinstance(verification_execution, dict):
        raise RunnerError("Coding run does not declare verification execution")
    if verification_execution.get("mode") != "deferred":
        raise RunnerError("Coding run was not generated for deferred verification")
    if verification_execution.get("completed_at") is not None:
        raise RunnerError("Deferred coding run has already been finalized")

    case_record = record.get("case")
    artifacts = record.get("artifacts")
    if not isinstance(case_record, dict) or not isinstance(artifacts, dict):
        raise RunnerError("Coding run is missing case or artifact metadata")
    case_path = Path(_relative_posix_path(case_record.get("case_path"), "run case"))
    loaded = load_coding_case(repo_root, case_path)
    expected_case_values = {
        "case_id": loaded["case"]["case_id"],
        "case_version": loaded["case"]["case_version"],
        "artifact_format": loaded["artifact_contract"]["format"],
        "fixture_manifest_sha256": loaded["manifest_sha256"],
        "task_sha256": loaded["task_sha256"],
        "verifier_version": loaded["case"]["verification"]["version"],
        "hidden_test_sha256": loaded["hidden_test_sha256"],
    }
    for key, expected in expected_case_values.items():
        if case_record.get(key) != expected:
            raise RunnerError(f"Deferred coding run case identity mismatch for {key}")

    response_relative = _relative_posix_path(
        artifacts.get("response"), "run response"
    )
    response_path = resolved_run_dir.joinpath(*PurePosixPath(response_relative).parts)
    if not response_path.is_file():
        raise RunnerError(f"Deferred coding response does not exist: {response_path}")
    expected_response_sha256 = artifacts.get("response_sha256")
    if (
        not isinstance(expected_response_sha256, str)
        or sha256_file(response_path) != expected_response_sha256
    ):
        raise RunnerError("Deferred coding response hash mismatch")
    response_text = response_path.read_text(encoding="utf-8").rstrip("\n")

    verification = verify_candidate_artifact(repo_root, case_path, response_text)
    write_json(resolved_run_dir / "verification.json", verification)
    record["outcome"] = {
        "output_status": verification["output_status"],
        "verification_status": verification["verification_status"],
        "task_status": verification["task_status"],
        "verified_success": verification["verified_success"],
        "failure_code": verification["failure_code"],
    }
    completed_at = utc_now()
    record["verification_execution"]["completed_at"] = completed_at
    record["verification_execution"]["runtime"] = (
        verification.get("tests", {}).get("runtime")
        if isinstance(verification.get("tests"), dict)
        else None
    )
    write_json(run_path, record)
    return {
        "run_id": record["run_id"],
        "run_dir": str(resolved_run_dir),
        "status": "complete",
        "track": "A",
        "model": record["deployment"]["model"]["requested_name"],
        "case_id": case_record["case_id"],
        "verified_success": verification["verified_success"],
        "failure_code": verification["failure_code"],
        "verification_completed_at": completed_at,
    }
