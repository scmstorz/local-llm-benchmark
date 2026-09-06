"""Local Ollama benchmark runner and comparison harness."""

from __future__ import annotations

import hashlib
import json
import os
import platform
import re
import secrets
import shutil
import subprocess
import time
from copy import deepcopy
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from .checks import evaluate_output
from .ollama import OllamaClient, OllamaError


DEFAULT_CASE_PATH = Path("tasks/summarization/dev/mit-sloan-ai-climate/case.json")
DEFAULT_SUITE_PATH = Path("tasks/capability-suite-v0.3.json")


class RunnerError(RuntimeError):
    """Raised for invalid cases or incomplete benchmark runs."""


@dataclass(frozen=True)
class RunConfig:
    model: str
    case_path: Path = DEFAULT_CASE_PATH
    host: str = "http://127.0.0.1:11434"
    results_dir: Path = Path("results/runs")
    temperature: float = 0.0
    seed: int = 42
    num_ctx: int = 8192
    num_predict: int = 2600
    think: bool | str = False
    keep_alive: str = "5m"
    timeout_seconds: float = 600.0
    comparison_id: str | None = None
    measurement_phase: str | None = None
    measurement_iteration: int | None = None


@dataclass(frozen=True)
class ComparisonConfig:
    models: tuple[str, ...]
    case_path: Path = DEFAULT_CASE_PATH
    host: str = "http://127.0.0.1:11434"
    results_dir: Path = Path("results/runs")
    comparisons_dir: Path = Path("results/comparisons")
    temperature: float = 0.0
    seed: int = 42
    num_ctx: int = 8192
    num_predict: int = 2600
    think: bool | str = False
    keep_alive: str = "10m"
    timeout_seconds: float = 600.0


@dataclass(frozen=True)
class SuiteConfig:
    model: str
    suite_path: Path = DEFAULT_SUITE_PATH
    host: str = "http://127.0.0.1:11434"
    results_dir: Path = Path("results/runs")
    sweeps_dir: Path = Path("results/sweeps")
    timeout_seconds: float | None = None


@dataclass(frozen=True)
class SuiteResumeConfig:
    sweep_dir: Path
    host: str = "http://127.0.0.1:11434"
    results_dir: Path = Path("results/runs")
    timeout_seconds: float | None = None


def utc_now() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def load_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise RunnerError(f"Required file does not exist: {path}") from exc
    except json.JSONDecodeError as exc:
        raise RunnerError(f"Invalid JSON in {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise RunnerError(f"Expected a JSON object in {path}")
    return value


def write_json(path: Path, value: Any) -> None:
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def git_commit(repo_root: Path) -> str | None:
    result = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=repo_root,
        capture_output=True,
        text=True,
        check=False,
    )
    return result.stdout.strip() if result.returncode == 0 else None


def memory_total_bytes() -> int | None:
    if platform.system() == "Darwin":
        result = subprocess.run(
            ["sysctl", "-n", "hw.memsize"],
            capture_output=True,
            text=True,
            check=False,
        )
        if result.returncode == 0 and result.stdout.strip().isdigit():
            return int(result.stdout.strip())
    try:
        page_size = os.sysconf("SC_PAGE_SIZE")
        page_count = os.sysconf("SC_PHYS_PAGES")
    except (AttributeError, OSError, ValueError):
        return None
    return int(page_size * page_count)


def resolve_repo_path(repo_root: Path, value: str | Path) -> Path:
    path = Path(value)
    return path if path.is_absolute() else repo_root / path


def load_case(repo_root: Path, case_path: Path) -> dict[str, Any]:
    resolved_case_path = resolve_repo_path(repo_root, case_path)
    case = load_json(resolved_case_path)
    metadata_path = resolve_repo_path(repo_root, case["input"]["source_metadata_path"])
    metadata = load_json(metadata_path)
    if case["input"].get("source_id") != metadata.get("source_id"):
        raise RunnerError(
            "Case source_id does not match the source metadata source_id"
        )
    input_config = case["input"]
    system_path = resolve_repo_path(repo_root, case["prompt"]["system_path"])
    user_template_path = resolve_repo_path(repo_root, case["prompt"]["user_template_path"])
    system_message = system_path.read_text(encoding="utf-8").strip()
    user_template = user_template_path.read_text(encoding="utf-8")
    source_delivery = case["prompt"].get("source_delivery", "candidate")

    artifact_declarations = input_config.get("candidate_artifacts")
    loaded_artifacts: list[dict[str, Any]] = []
    if artifact_declarations is not None:
        if source_delivery != "candidate":
            raise RunnerError(
                "candidate_artifacts require prompt source_delivery='candidate'"
            )
        if not isinstance(artifact_declarations, list) or not artifact_declarations:
            raise RunnerError("candidate_artifacts must be a non-empty list")

        seen_ids: set[str] = set()
        seen_placeholders: set[str] = set()
        seen_bundle_names: set[str] = set()
        user_message = user_template
        for declaration in artifact_declarations:
            if not isinstance(declaration, dict):
                raise RunnerError("Every candidate artifact must be an object")
            artifact_id = declaration.get("id")
            path_value = declaration.get("path")
            artifact_key = declaration.get("metadata_artifact_key")
            placeholder = declaration.get("placeholder")
            if not all(
                isinstance(value, str) and value
                for value in (artifact_id, path_value, artifact_key, placeholder)
            ):
                raise RunnerError(
                    "Every candidate artifact must define id, path, "
                    "metadata_artifact_key and placeholder"
                )
            if artifact_id in seen_ids:
                raise RunnerError(f"Duplicate candidate artifact id: {artifact_id}")
            if placeholder in seen_placeholders:
                raise RunnerError(
                    f"Duplicate candidate artifact placeholder: {placeholder}"
                )
            if user_template.count(placeholder) != 1:
                raise RunnerError(
                    f"Expected exactly one {placeholder} placeholder in {user_template_path}"
                )

            bundle_name = declaration.get(
                "judge_bundle_name", f"{safe_slug(artifact_id)}.md"
            )
            if (
                not isinstance(bundle_name, str)
                or not bundle_name
                or Path(bundle_name).name != bundle_name
            ):
                raise RunnerError(
                    f"Invalid judge_bundle_name for candidate artifact {artifact_id}"
                )
            if bundle_name in seen_bundle_names:
                raise RunnerError(f"Duplicate judge bundle source name: {bundle_name}")

            artifact_path = resolve_repo_path(repo_root, path_value)
            if not artifact_path.exists():
                raise RunnerError(
                    f"Candidate artifact is missing: {artifact_path}. "
                    "See the case README for setup."
                )
            try:
                expected_hash = metadata["artifacts"][artifact_key]["sha256"]
            except KeyError as exc:
                raise RunnerError(
                    f"Source metadata does not define artifact {artifact_key!r}"
                ) from exc
            actual_hash = sha256_file(artifact_path)
            if actual_hash != expected_hash:
                raise RunnerError(
                    f"Source hash mismatch for {artifact_path}: "
                    f"expected {expected_hash}, got {actual_hash}"
                )

            user_message = user_message.replace(
                placeholder, artifact_path.read_text(encoding="utf-8")
            )
            loaded_artifacts.append(
                {
                    "id": artifact_id,
                    "path": artifact_path,
                    "sha256": actual_hash,
                    "metadata_artifact_key": artifact_key,
                    "judge_bundle_name": bundle_name,
                    "candidate_visible": True,
                }
            )
            seen_ids.add(artifact_id)
            seen_placeholders.add(placeholder)
            seen_bundle_names.add(bundle_name)
        user_message = user_message.strip()
    else:
        source_path_value = input_config.get(
            "reference_source_path"
        ) or input_config.get("private_source_path")
        if not source_path_value:
            raise RunnerError(
                "Case input must define candidate_artifacts, reference_source_path "
                "or private_source_path"
            )
        source_path = resolve_repo_path(repo_root, source_path_value)
        if not source_path.exists():
            raise RunnerError(
                f"Source is missing: {source_path}. See the case README for setup."
            )
        source_artifact_key = input_config.get("source_artifact_key", "clean_source")
        try:
            expected_hash = metadata["artifacts"][source_artifact_key]["sha256"]
        except KeyError as exc:
            raise RunnerError(
                f"Source metadata does not define artifact {source_artifact_key!r}"
            ) from exc
        actual_hash = sha256_file(source_path)
        if actual_hash != expected_hash:
            raise RunnerError(
                f"Source hash mismatch for {source_path}: "
                f"expected {expected_hash}, got {actual_hash}"
            )

        placeholder = case["prompt"].get("source_placeholder")
        if source_delivery == "candidate":
            if not placeholder or user_template.count(placeholder) != 1:
                raise RunnerError(
                    f"Expected exactly one source placeholder in {user_template_path}"
                )
            user_message = user_template.replace(
                placeholder, source_path.read_text(encoding="utf-8")
            ).strip()
        elif source_delivery == "judge_only":
            if placeholder and placeholder in user_template:
                raise RunnerError(
                    f"Judge-only source placeholder must not appear in {user_template_path}"
                )
            user_message = user_template.strip()
        else:
            raise RunnerError(f"Unsupported prompt source_delivery: {source_delivery!r}")
        loaded_artifacts.append(
            {
                "id": "source",
                "path": source_path,
                "sha256": actual_hash,
                "metadata_artifact_key": source_artifact_key,
                "judge_bundle_name": "source.md",
                "candidate_visible": source_delivery == "candidate",
            }
        )

    primary_artifact = loaded_artifacts[0]
    return {
        "case": case,
        "case_path": resolved_case_path,
        "source_metadata": metadata,
        "source_path": primary_artifact["path"],
        "source_hash": primary_artifact["sha256"],
        "input_artifacts": loaded_artifacts,
        "system_message": system_message,
        "user_message": user_message,
    }


def load_suite_manifest(repo_root: Path, suite_path: Path) -> dict[str, Any]:
    """Load and validate a manifest for a one-model capability sweep."""
    resolved_path = resolve_repo_path(repo_root, suite_path)
    manifest = load_json(resolved_path)
    cases = manifest.get("cases")
    methodology = manifest.get("methodology")
    if not isinstance(cases, list) or not cases:
        raise RunnerError("Suite manifest must define a non-empty cases list")
    if not isinstance(methodology, dict):
        raise RunnerError("Suite manifest must define methodology settings")
    expected_positions = list(range(1, len(cases) + 1))
    actual_positions = [entry.get("position") for entry in cases if isinstance(entry, dict)]
    if actual_positions != expected_positions:
        raise RunnerError("Suite case positions must be unique and contiguous from one")

    seen_paths: set[str] = set()
    loaded_cases: list[dict[str, Any]] = []
    for entry in cases:
        case_path = entry.get("case_path")
        num_ctx = entry.get("num_ctx")
        if not isinstance(case_path, str) or not case_path:
            raise RunnerError("Every suite case must define a case_path string")
        if case_path in seen_paths:
            raise RunnerError(f"Duplicate suite case path: {case_path}")
        seen_paths.add(case_path)
        if not isinstance(num_ctx, int) or num_ctx < 1:
            raise RunnerError(f"Suite case {case_path} must define a positive num_ctx")
        loaded = load_case(repo_root, Path(case_path))
        validate_context_window(loaded["case"], num_ctx)
        loaded_cases.append({"entry": entry, "loaded_case": loaded})

    required_settings = {
        "temperature": (int, float),
        "seed": int,
        "think": (bool, str),
        "num_predict": int,
        "keep_alive": str,
        "timeout_seconds": (int, float),
    }
    for key, expected_type in required_settings.items():
        value = methodology.get(key)
        if isinstance(value, bool) and key in {"temperature", "seed", "num_predict", "timeout_seconds"}:
            raise RunnerError(f"Suite methodology {key} has an invalid value")
        if not isinstance(value, expected_type):
            raise RunnerError(f"Suite methodology must define {key}")
    return {
        "manifest": manifest,
        "path": resolved_path,
        "sha256": sha256_file(resolved_path),
        "cases": loaded_cases,
    }


def validate_context_window(case: dict[str, Any], configured_num_ctx: int) -> None:
    """Reject a context setting below a case's declared minimum."""
    minimum_num_ctx = case.get("input", {}).get("minimum_num_ctx")
    if minimum_num_ctx is None:
        return
    if not isinstance(minimum_num_ctx, int) or minimum_num_ctx < 1:
        raise RunnerError(
            f"Case {case.get('case_id', '<unknown>')} has an invalid minimum_num_ctx"
        )
    if configured_num_ctx < minimum_num_ctx:
        raise RunnerError(
            f"Case {case['case_id']} requires --num-ctx {minimum_num_ctx} or greater; "
            f"received {configured_num_ctx}"
        )


def find_model(models_response: dict[str, Any], requested_model: str) -> dict[str, Any]:
    models = models_response.get("models", [])
    for model in models:
        if model.get("name") == requested_model or model.get("model") == requested_model:
            return model
    available = sorted(
        model.get("name", "") for model in models if isinstance(model, dict) and model.get("name")
    )
    raise RunnerError(
        f"Ollama model {requested_model!r} is not installed. Available: {', '.join(available)}"
    )


def nanoseconds_to_seconds(value: Any) -> float | None:
    if not isinstance(value, (int, float)):
        return None
    return value / 1_000_000_000


def tokens_per_second(count: Any, duration_ns: Any) -> float | None:
    if not isinstance(count, (int, float)) or not isinstance(duration_ns, (int, float)):
        return None
    if duration_ns <= 0:
        return None
    return count / (duration_ns / 1_000_000_000)


def safe_slug(value: str) -> str:
    slug = re.sub(r"[^a-zA-Z0-9]+", "-", value).strip("-").lower()
    return slug or "run"


def copy_judge_artifact(repo_root: Path, bundle_dir: Path, relative_path: str) -> Path:
    source = resolve_repo_path(repo_root, relative_path)
    destination = bundle_dir / relative_path
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, destination)
    return destination


def create_batch_judge_bundle(
    *,
    repo_root: Path,
    bundle_dir: Path,
    bundle_id: str,
    loaded_case: dict[str, Any],
    candidates: list[dict[str, Any]],
) -> Path:
    case = loaded_case["case"]
    (bundle_dir / "candidates").mkdir(parents=True, exist_ok=True)
    (bundle_dir / "checks").mkdir(parents=True, exist_ok=True)
    (bundle_dir / "source").mkdir(parents=True, exist_ok=True)

    copied_paths: list[Path] = []
    copied_paths.append(copy_judge_artifact(repo_root, bundle_dir, str(loaded_case["case_path"].relative_to(repo_root))))
    copied_paths.append(copy_judge_artifact(repo_root, bundle_dir, case["input"]["source_metadata_path"]))
    copied_paths.append(copy_judge_artifact(repo_root, bundle_dir, case["prompt"]["system_path"]))
    copied_paths.append(copy_judge_artifact(repo_root, bundle_dir, case["prompt"]["user_template_path"]))
    copied_paths.append(copy_judge_artifact(repo_root, bundle_dir, case["evaluation"]["benchmark_card_path"]))
    copied_paths.append(copy_judge_artifact(repo_root, bundle_dir, case["evaluation"]["judge_instructions_path"]))
    copied_paths.append(copy_judge_artifact(repo_root, bundle_dir, case["evaluation"]["judge_result_schema_path"]))

    for artifact in loaded_case["input_artifacts"]:
        source_copy = bundle_dir / "source" / artifact["judge_bundle_name"]
        shutil.copy2(artifact["path"], source_copy)
        copied_paths.append(source_copy)

    for candidate in candidates:
        candidate_id = candidate["candidate_id"]
        candidate_path = bundle_dir / "candidates" / f"{candidate_id}.md"
        candidate_path.write_text(candidate["response_text"].rstrip() + "\n", encoding="utf-8")
        copied_paths.append(candidate_path)
        checks_path = bundle_dir / "checks" / f"{candidate_id}.json"
        write_json(checks_path, candidate["checks"])
        copied_paths.append(checks_path)

    manifest = {
        "schema_version": "1.0.0",
        "bundle_id": bundle_id,
        "created_at": utc_now(),
        "case_id": case["case_id"],
        "case_version": case["case_version"],
        "benchmark_card_version": case["evaluation"]["benchmark_card_version"],
        "judge_instructions_version": case["evaluation"]["judge_instructions_version"],
        "candidate_ids": [candidate["candidate_id"] for candidate in candidates],
        "anonymized": True,
        "model_identity_included": False,
        "artifacts": [
            {
                "path": str(path.relative_to(bundle_dir)),
                "sha256": sha256_file(path),
            }
            for path in sorted(copied_paths)
        ],
    }
    write_json(bundle_dir / "manifest.json", manifest)
    return bundle_dir


def create_judge_bundle(
    *,
    repo_root: Path,
    run_dir: Path,
    loaded_case: dict[str, Any],
    candidate_id: str,
    response_text: str,
    checks: dict[str, Any],
) -> Path:
    return create_batch_judge_bundle(
        repo_root=repo_root,
        bundle_dir=run_dir / "judge-bundle",
        bundle_id=f"judge-bundle-{run_dir.name}",
        loaded_case=loaded_case,
        candidates=[
            {
                "candidate_id": candidate_id,
                "response_text": response_text,
                "checks": checks,
            }
        ],
    )


def run_once(repo_root: Path, config: RunConfig) -> dict[str, Any]:
    measurement_values = (
        config.comparison_id,
        config.measurement_phase,
        config.measurement_iteration,
    )
    if any(value is None for value in measurement_values) and any(
        value is not None for value in measurement_values
    ):
        raise RunnerError(
            "comparison_id, measurement_phase and measurement_iteration must be set together"
        )
    if config.measurement_phase not in {None, "cold", "warm"}:
        raise RunnerError("measurement_phase must be cold, warm, or unset")
    if config.measurement_iteration is not None and config.measurement_iteration < 1:
        raise RunnerError("measurement_iteration must be at least one")

    loaded_case = load_case(repo_root, config.case_path)
    case = loaded_case["case"]
    validate_context_window(case, config.num_ctx)
    client = OllamaClient(config.host, timeout_seconds=config.timeout_seconds)
    version_response = client.version()
    model_tag = find_model(client.list_models(), config.model)
    model_show = client.show_model(config.model)

    timestamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    run_id = f"run-{timestamp}-{secrets.token_hex(4)}"
    candidate_id = f"candidate-{secrets.token_hex(6)}"
    results_dir = resolve_repo_path(repo_root, config.results_dir)
    run_dir = results_dir / run_id
    run_dir.mkdir(parents=True, exist_ok=False)

    options = {
        "temperature": config.temperature,
        "seed": config.seed,
        "num_ctx": config.num_ctx,
        "num_predict": config.num_predict,
    }
    messages = [
        {"role": "system", "content": loaded_case["system_message"]},
        {"role": "user", "content": loaded_case["user_message"]},
    ]
    request_payload = {
        "model": config.model,
        "messages": messages,
        "stream": True,
        "think": config.think,
        "keep_alive": config.keep_alive,
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

    stream_path = run_dir / "stream.ndjson"
    try:
        with stream_path.open("w", encoding="utf-8") as stream_file:
            for event in client.stream_chat(request_payload):
                stream_file.write(json.dumps(event, ensure_ascii=False, separators=(",", ":")) + "\n")
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
                "status": "failed",
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
    (run_dir / "response.md").write_text(response_text + "\n", encoding="utf-8")
    if thinking_text:
        (run_dir / "thinking.md").write_text(thinking_text + "\n", encoding="utf-8")

    checks = evaluate_output(response_text, case["output"]["maximum_words"])
    checks["generation_done_reason"] = final_event.get("done_reason")
    checks["generation_complete"] = final_event.get("done_reason") != "length"
    write_json(run_dir / "checks.json", checks)

    metrics = {
        "wall_time_seconds": wall_time_seconds,
        "time_to_first_content_seconds": first_content_seconds,
        "time_to_first_content_definition": "Client wall time from request start to the first non-empty assistant content chunk; not token-level TTFT.",
        "total_duration_ns": final_event.get("total_duration"),
        "total_duration_seconds": nanoseconds_to_seconds(final_event.get("total_duration")),
        "load_duration_ns": final_event.get("load_duration"),
        "load_duration_seconds": nanoseconds_to_seconds(final_event.get("load_duration")),
        "prompt_eval_count": final_event.get("prompt_eval_count"),
        "prompt_eval_duration_ns": final_event.get("prompt_eval_duration"),
        "prompt_eval_duration_seconds": nanoseconds_to_seconds(final_event.get("prompt_eval_duration")),
        "prompt_tokens_per_second": tokens_per_second(
            final_event.get("prompt_eval_count"), final_event.get("prompt_eval_duration")
        ),
        "eval_count": final_event.get("eval_count"),
        "eval_duration_ns": final_event.get("eval_duration"),
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
    run_record = {
        "schema_version": "1.0.0",
        "run_id": run_id,
        "candidate_id": candidate_id,
        "status": "complete",
        "started_at": started_at,
        "completed_at": utc_now(),
        "case": {
            "case_id": case["case_id"],
            "case_version": case["case_version"],
            "prompt_version": case["prompt"]["version"],
            "benchmark_card_version": case["evaluation"]["benchmark_card_version"],
            "source_id": loaded_case["source_metadata"]["source_id"],
            "source_sha256": loaded_case["source_hash"],
            "input_artifacts": [
                {
                    "id": artifact["id"],
                    "sha256": artifact["sha256"],
                    "candidate_visible": artifact["candidate_visible"],
                }
                for artifact in loaded_case["input_artifacts"]
            ],
        },
        "deployment": {
            "ollama_host": client.host,
            "ollama_version": version_response.get("version"),
            "model": model_record,
            "options": options,
            "think": config.think,
            "keep_alive": config.keep_alive,
            "hardware": {
                "system": platform.system(),
                "release": platform.release(),
                "machine": platform.machine(),
                "processor": platform.processor() or None,
                "memory_total_bytes": memory_total_bytes(),
            },
        },
        "execution": {
            "endpoint": "/api/chat",
            "stream": True,
            "done_reason": final_event.get("done_reason"),
            "git_commit": git_commit(repo_root),
            "python_version": platform.python_version(),
        },
        "measurement": (
            {
                "comparison_id": config.comparison_id,
                "phase": config.measurement_phase,
                "iteration": config.measurement_iteration,
            }
            if config.comparison_id is not None
            else None
        ),
        "metrics": metrics,
        "checks": checks,
        "artifacts": {
            "request": "request.json",
            "raw_stream": "stream.ndjson",
            "response": "response.md",
            "thinking": "thinking.md" if thinking_text else None,
            "ollama_show": "ollama-show.json",
            "judge_bundle": "judge-bundle",
        },
    }
    write_json(run_dir / "run.json", run_record)
    write_json(
        run_dir / "candidate-map.json",
        {
            "schema_version": "1.0.0",
            "private_model_mapping": {candidate_id: config.model},
        },
    )
    bundle_dir = create_judge_bundle(
        repo_root=repo_root,
        run_dir=run_dir,
        loaded_case=loaded_case,
        candidate_id=candidate_id,
        response_text=response_text,
        checks=checks,
    )
    run_record["artifacts"]["judge_bundle"] = str(bundle_dir.relative_to(run_dir))
    write_json(run_dir / "run.json", run_record)

    return {
        "run_id": run_id,
        "run_dir": str(run_dir),
        "candidate_id": candidate_id,
        "model": config.model,
        "status": "complete",
        "done_reason": final_event.get("done_reason"),
        "comparison_id": config.comparison_id,
        "measurement_phase": config.measurement_phase,
        "measurement_iteration": config.measurement_iteration,
        "checks": checks,
        "metrics": metrics,
    }


def running_model_names(response: dict[str, Any]) -> list[str]:
    return sorted(
        str(model.get("name") or model.get("model"))
        for model in response.get("models", [])
        if isinstance(model, dict) and (model.get("name") or model.get("model"))
    )


def comparison_run_config(
    config: ComparisonConfig,
    *,
    model: str,
    comparison_id: str,
    phase: str,
    iteration: int = 1,
) -> RunConfig:
    return RunConfig(
        model=model,
        case_path=config.case_path,
        host=config.host,
        results_dir=config.results_dir,
        temperature=config.temperature,
        seed=config.seed,
        num_ctx=config.num_ctx,
        num_predict=config.num_predict,
        think=config.think,
        keep_alive=config.keep_alive,
        timeout_seconds=config.timeout_seconds,
        comparison_id=comparison_id,
        measurement_phase=phase,
        measurement_iteration=iteration,
    )


def compact_run_result(result: dict[str, Any]) -> dict[str, Any]:
    return {
        "run_id": result["run_id"],
        "measurement_phase": result["measurement_phase"],
        "measurement_iteration": result["measurement_iteration"],
        "status": result["status"],
        "done_reason": result["done_reason"],
        "checks": result["checks"],
        "metrics": result["metrics"],
    }


def comparison_completion_result(
    *,
    comparison_dir: Path,
    record: dict[str, Any],
    quality_candidate_count: int,
) -> dict[str, Any]:
    """Return a console-safe comparison result without model identity mapping."""
    return {
        "comparison_id": record["comparison_id"],
        "comparison_dir": str(comparison_dir),
        "status": record["status"],
        "model_count": len(record["models"]),
        "quality_candidate_count": quality_candidate_count,
        "judge_bundle": str(comparison_dir / "judge-bundle"),
        "blinding_notice": (
            "The explicit candidate-to-model mapping is intentionally withheld "
            "from console output and stored in candidate-map.json."
        ),
    }


def run_completion_result(result: dict[str, Any]) -> dict[str, Any]:
    """Return console-safe single-run metadata without the private mapping."""
    return {
        "run_id": result["run_id"],
        "run_dir": result["run_dir"],
        "status": result["status"],
        "done_reason": result["done_reason"],
        "checks": result["checks"],
        "metrics": result["metrics"],
        "judge_bundle": str(Path(result["run_dir"]) / "judge-bundle"),
        "blinding_notice": (
            "The explicit candidate-to-model mapping is intentionally withheld "
            "from console output and stored in candidate-map.json."
        ),
    }


def run_cold_warm_comparison(
    repo_root: Path,
    config: ComparisonConfig,
) -> dict[str, Any]:
    if len(config.models) < 2:
        raise RunnerError("A comparison requires at least two models")
    if len(set(config.models)) != len(config.models):
        raise RunnerError("Comparison model names must be unique")

    loaded_case = load_case(repo_root, config.case_path)
    validate_context_window(loaded_case["case"], config.num_ctx)
    client = OllamaClient(config.host, timeout_seconds=config.timeout_seconds)
    version_response = client.version()
    installed_models = client.list_models()
    for model in config.models:
        find_model(installed_models, model)

    timestamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    comparison_id = f"comparison-{timestamp}-{secrets.token_hex(4)}"
    comparisons_dir = resolve_repo_path(repo_root, config.comparisons_dir)
    comparison_dir = comparisons_dir / comparison_id
    comparison_dir.mkdir(parents=True, exist_ok=False)
    comparison_path = comparison_dir / "comparison.json"

    record: dict[str, Any] = {
        "schema_version": "1.0.0",
        "comparison_id": comparison_id,
        "status": "running",
        "started_at": utc_now(),
        "completed_at": None,
        "case": {
            "case_id": loaded_case["case"]["case_id"],
            "case_version": loaded_case["case"]["case_version"],
            "prompt_version": loaded_case["case"]["prompt"]["version"],
            "source_sha256": loaded_case["source_hash"],
        },
        "ollama_version": version_response.get("version"),
        "methodology": {
            "cold_runs_per_model": 1,
            "warm_runs_per_model": 1,
            "cold_definition": "All models reported by Ollama as running were explicitly unloaded before the cold request.",
            "warm_definition": "The warm request immediately followed the cold request with the same model and generation settings.",
            "quality_candidate_phase": "warm",
            "additional_warm_runs": "Only if initial measurements are close or unstable.",
        },
        "options": {
            "temperature": config.temperature,
            "seed": config.seed,
            "num_ctx": config.num_ctx,
            "num_predict": config.num_predict,
            "think": config.think,
            "keep_alive": config.keep_alive,
        },
        "models": [],
        "artifacts": {
            "candidate_map": "candidate-map.json",
            "judge_bundle": "judge-bundle",
        },
    }
    write_json(comparison_path, record)

    candidate_mapping: dict[str, Any] = {}
    judge_candidates: list[dict[str, Any]] = []
    try:
        for model in config.models:
            before_unload = running_model_names(client.list_running_models())
            for running_model in before_unload:
                client.unload_model(running_model)
            after_unload = running_model_names(client.list_running_models())
            if after_unload:
                raise RunnerError(
                    "Ollama still reports models as loaded after explicit unload: "
                    + ", ".join(after_unload)
                )

            cold = run_once(
                repo_root,
                comparison_run_config(
                    config,
                    model=model,
                    comparison_id=comparison_id,
                    phase="cold",
                ),
            )
            warm = run_once(
                repo_root,
                comparison_run_config(
                    config,
                    model=model,
                    comparison_id=comparison_id,
                    phase="warm",
                ),
            )
            warm_run_dir = Path(warm["run_dir"])
            judge_candidates.append(
                {
                    "candidate_id": warm["candidate_id"],
                    "response_text": (warm_run_dir / "response.md").read_text(encoding="utf-8"),
                    "checks": warm["checks"],
                }
            )
            candidate_mapping[warm["candidate_id"]] = {
                "model": model,
                "run_id": warm["run_id"],
                "measurement_phase": "warm",
            }
            record["models"].append(
                {
                    "model": model,
                    "running_models_before_unload": before_unload,
                    "running_models_after_unload": after_unload,
                    "cold": compact_run_result(cold),
                    "warm": compact_run_result(warm),
                }
            )
            write_json(comparison_path, record)

        write_json(
            comparison_dir / "candidate-map.json",
            {
                "schema_version": "1.0.0",
                "private_model_mapping": candidate_mapping,
            },
        )
        create_batch_judge_bundle(
            repo_root=repo_root,
            bundle_dir=comparison_dir / "judge-bundle",
            bundle_id=f"judge-bundle-{comparison_id}",
            loaded_case=loaded_case,
            candidates=judge_candidates,
        )
        record["status"] = "complete"
        record["completed_at"] = utc_now()
        write_json(comparison_path, record)
    except Exception as exc:
        record["status"] = "failed"
        record["completed_at"] = utc_now()
        record["error"] = {"type": type(exc).__name__, "message": str(exc)}
        write_json(comparison_path, record)
        raise

    return comparison_completion_result(
        comparison_dir=comparison_dir,
        record=record,
        quality_candidate_count=len(judge_candidates),
    )


def suite_completion_result(record: dict[str, Any], sweep_dir: Path) -> dict[str, Any]:
    """Return a console-safe suite result without candidate or model mappings."""
    return {
        "sweep_id": record["sweep_id"],
        "sweep_dir": str(sweep_dir),
        "status": record["status"],
        "case_count": record["case_count"],
        "complete_case_count": record["complete_case_count"],
        "failed_case_count": record["failed_case_count"],
        "quality_candidate_count": record["quality_candidate_count"],
        "blinding_notice": (
            "Candidate IDs and their explicit model mapping are withheld from console "
            "output and stored in candidate-map.json."
        ),
    }


def _new_suite_case_record(
    entry: dict[str, Any], loaded_case: dict[str, Any]
) -> dict[str, Any]:
    case = loaded_case["case"]
    return {
        "position": entry["position"],
        "case_id": case["case_id"],
        "case_path": entry["case_path"],
        "canonical_baseline_available": entry.get(
            "canonical_baseline_available", False
        ),
        "status": "running",
        "running_models_before_unload": [],
        "running_models_after_unload": [],
        "cold": None,
        "warm": None,
        "error": None,
        "interrupted_attempts": [],
    }


def preserve_interrupted_suite_case(
    case_record: dict[str, Any],
    entry: dict[str, Any],
    loaded_case: dict[str, Any],
) -> dict[str, Any]:
    """Reset an unfinished case while retaining every recorded partial attempt."""
    if case_record.get("status") != "running":
        raise RunnerError("Only a running suite case can be resumed")
    previous_attempts = case_record.get("interrupted_attempts", [])
    if not isinstance(previous_attempts, list):
        raise RunnerError("Suite case interrupted_attempts must be a list")
    snapshot = {
        key: deepcopy(value)
        for key, value in case_record.items()
        if key != "interrupted_attempts"
    }
    snapshot["preserved_at"] = utc_now()
    snapshot["interruption_class"] = "process_ended_before_case_terminal_state"
    replacement = _new_suite_case_record(entry, loaded_case)
    replacement["interrupted_attempts"] = [*deepcopy(previous_attempts), snapshot]
    replacement["resume_attempt"] = len(replacement["interrupted_attempts"])
    return replacement


def _recount_suite_cases(record: dict[str, Any]) -> None:
    cases = record.get("cases", [])
    record["complete_case_count"] = sum(
        case.get("status") == "complete" for case in cases
    )
    record["failed_case_count"] = sum(case.get("status") == "failed" for case in cases)
    record["quality_candidate_count"] = record["complete_case_count"]


def _execute_suite_case_pair(
    *,
    repo_root: Path,
    client: OllamaClient,
    record: dict[str, Any],
    sweep_path: Path,
    sweep_id: str,
    model: str,
    host: str,
    results_dir: Path,
    methodology: dict[str, Any],
    timeout_seconds: float,
    entry: dict[str, Any],
    loaded_case: dict[str, Any],
    case_record: dict[str, Any],
) -> dict[str, Any]:
    """Execute one fresh cold/warm pair and checkpoint after the cold request."""
    case = loaded_case["case"]
    before_unload = running_model_names(client.list_running_models())
    unexpected = [name for name in before_unload if name != model]
    if unexpected:
        raise RunnerError(
            "Unexpected Ollama model activity before suite case "
            f"{case['case_id']}: {', '.join(unexpected)}"
        )
    case_record["running_models_before_unload"] = before_unload
    for running_model in before_unload:
        client.unload_model(running_model)
    after_unload = running_model_names(client.list_running_models())
    case_record["running_models_after_unload"] = after_unload
    if after_unload:
        raise RunnerError(
            "Ollama still reports models after explicit unload: "
            + ", ".join(after_unload)
        )

    run_settings = {
        "model": model,
        "case_path": Path(entry["case_path"]),
        "host": host,
        "results_dir": results_dir,
        "temperature": float(methodology["temperature"]),
        "seed": int(methodology["seed"]),
        "num_ctx": int(entry["num_ctx"]),
        "num_predict": int(methodology["num_predict"]),
        "think": methodology["think"],
        "keep_alive": str(methodology["keep_alive"]),
        "timeout_seconds": timeout_seconds,
        "comparison_id": sweep_id,
        "measurement_iteration": 1,
    }
    cold = run_once(
        repo_root,
        RunConfig(**run_settings, measurement_phase="cold"),
    )
    case_record["cold"] = compact_run_result(cold)
    write_json(sweep_path, record)
    warm = run_once(
        repo_root,
        RunConfig(**run_settings, measurement_phase="warm"),
    )
    case_record["warm"] = compact_run_result(warm)
    case_record["status"] = "complete"
    case_record["error"] = None
    return {
        "candidate_id": warm["candidate_id"],
        "model": model,
        "case_id": case["case_id"],
        "run_id": warm["run_id"],
        "measurement_phase": "warm",
    }


def _suite_candidate_mapping(
    *,
    record: dict[str, Any],
    results_dir: Path,
) -> dict[str, Any]:
    mapping: dict[str, Any] = {}
    expected_model = record.get("deployment", {}).get("model")
    for case_record in record.get("cases", []):
        if case_record.get("status") != "complete":
            continue
        warm = case_record.get("warm")
        if not isinstance(warm, dict) or not isinstance(warm.get("run_id"), str):
            raise RunnerError(
                f"Complete suite case has no warm run: {case_record.get('case_id')}"
            )
        run_id = warm["run_id"]
        run = load_json(results_dir / run_id / "run.json")
        if run.get("status") != "complete":
            raise RunnerError(f"Suite candidate run is not complete: {run_id}")
        if run.get("case", {}).get("case_id") != case_record.get("case_id"):
            raise RunnerError(f"Suite candidate case mismatch: {run_id}")
        requested_model = (
            run.get("deployment", {}).get("model", {}).get("requested_name")
        )
        if requested_model != expected_model:
            raise RunnerError(f"Suite candidate model mismatch: {run_id}")
        measurement = run.get("measurement", {})
        if measurement.get("comparison_id") != record.get("sweep_id"):
            raise RunnerError(f"Suite candidate sweep mismatch: {run_id}")
        if measurement.get("phase") != "warm":
            raise RunnerError(f"Suite candidate is not a warm run: {run_id}")
        candidate_id = _require_nonempty_run_string(run, "candidate_id", run_id)
        mapping[candidate_id] = {
            "model": expected_model,
            "case_id": case_record["case_id"],
            "run_id": run_id,
            "measurement_phase": "warm",
        }
    return mapping


def _require_nonempty_run_string(run: dict[str, Any], key: str, context: str) -> str:
    value = run.get(key)
    if not isinstance(value, str) or not value:
        raise RunnerError(f"Suite run {context} has no {key}")
    return value


def run_model_suite(repo_root: Path, config: SuiteConfig) -> dict[str, Any]:
    """Run one cold and one immediate warm request for every manifest case."""
    loaded_suite = load_suite_manifest(repo_root, config.suite_path)
    manifest = loaded_suite["manifest"]
    methodology = manifest["methodology"]
    timeout_seconds = (
        config.timeout_seconds
        if config.timeout_seconds is not None
        else float(methodology["timeout_seconds"])
    )
    client = OllamaClient(config.host, timeout_seconds=timeout_seconds)
    version_response = client.version()
    model_tag = find_model(client.list_models(), config.model)

    timestamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    sweep_id = f"sweep-{timestamp}-{secrets.token_hex(4)}"
    sweeps_dir = resolve_repo_path(repo_root, config.sweeps_dir)
    sweep_dir = sweeps_dir / sweep_id
    sweep_dir.mkdir(parents=True, exist_ok=False)
    sweep_path = sweep_dir / "sweep.json"

    record: dict[str, Any] = {
        "schema_version": "1.0.0",
        "sweep_id": sweep_id,
        "status": "running",
        "started_at": utc_now(),
        "completed_at": None,
        "suite": {
            "suite_id": manifest.get("suite_id"),
            "suite_version": manifest.get("suite_version"),
            "manifest_path": str(loaded_suite["path"].relative_to(repo_root)),
            "manifest_sha256": loaded_suite["sha256"],
        },
        "deployment": {
            "model": config.model,
            "digest": model_tag.get("digest"),
            "size_bytes": model_tag.get("size"),
            "details": model_tag.get("details"),
            "ollama_version": version_response.get("version"),
        },
        "methodology": {
            **methodology,
            "cold_definition": "All models reported by Ollama were explicitly unloaded before each cold request.",
            "warm_definition": "The warm request immediately followed the cold request for the same case.",
        },
        "case_count": len(loaded_suite["cases"]),
        "complete_case_count": 0,
        "failed_case_count": 0,
        "quality_candidate_count": 0,
        "cases": [],
        "final_running_models": None,
        "resume_history": [],
        "artifacts": {"candidate_map": "candidate-map.json"},
    }
    write_json(sweep_path, record)

    candidate_mapping: dict[str, Any] = {}
    for suite_case in loaded_suite["cases"]:
        entry = suite_case["entry"]
        loaded_case = suite_case["loaded_case"]
        case_record = _new_suite_case_record(entry, loaded_case)
        record["cases"].append(case_record)
        write_json(sweep_path, record)
        try:
            mapping = _execute_suite_case_pair(
                repo_root=repo_root,
                client=client,
                record=record,
                sweep_path=sweep_path,
                sweep_id=sweep_id,
                model=config.model,
                host=config.host,
                results_dir=config.results_dir,
                methodology=methodology,
                timeout_seconds=timeout_seconds,
                entry=entry,
                loaded_case=loaded_case,
                case_record=case_record,
            )
            record["complete_case_count"] += 1
            record["quality_candidate_count"] += 1
            candidate_mapping[mapping["candidate_id"]] = {
                key: value for key, value in mapping.items() if key != "candidate_id"
            }
        except Exception as exc:
            case_record["status"] = "failed"
            case_record["error"] = {
                "type": type(exc).__name__,
                "message": str(exc),
            }
            record["failed_case_count"] += 1
        write_json(sweep_path, record)

    final_running = running_model_names(client.list_running_models())
    for running_model in final_running:
        client.unload_model(running_model)
    record["final_running_models"] = running_model_names(client.list_running_models())
    record["status"] = (
        "complete" if record["failed_case_count"] == 0 else "complete_with_failures"
    )
    record["completed_at"] = utc_now()
    write_json(
        sweep_dir / "candidate-map.json",
        {
            "schema_version": "1.0.0",
            "private_model_mapping": candidate_mapping,
        },
    )
    write_json(sweep_path, record)
    return suite_completion_result(record, sweep_dir)


def resume_model_suite(
    repo_root: Path,
    config: SuiteResumeConfig,
) -> dict[str, Any]:
    """Resume only unfinished suite cases while preserving partial attempts."""
    sweep_dir = resolve_repo_path(repo_root, config.sweep_dir)
    sweep_path = sweep_dir / "sweep.json"
    record = load_json(sweep_path)
    if record.get("status") not in {"running", "complete", "complete_with_failures"}:
        raise RunnerError("Suite resume requires a running or completed sweep record")
    sweep_id = _require_nonempty_run_string(record, "sweep_id", str(sweep_path))
    suite_record = record.get("suite", {})
    manifest_path_value = suite_record.get("manifest_path")
    if not isinstance(manifest_path_value, str) or not manifest_path_value:
        raise RunnerError("Suite sweep has no manifest_path")
    loaded_suite = load_suite_manifest(repo_root, Path(manifest_path_value))
    manifest = loaded_suite["manifest"]
    if loaded_suite["sha256"] != suite_record.get("manifest_sha256"):
        raise RunnerError("Suite manifest changed after the sweep was created")
    if manifest.get("suite_id") != suite_record.get("suite_id"):
        raise RunnerError("Suite identity changed after the sweep was created")
    if manifest.get("suite_version") != suite_record.get("suite_version"):
        raise RunnerError("Suite version changed after the sweep was created")
    if record.get("case_count") != len(loaded_suite["cases"]):
        raise RunnerError("Suite case count changed after the sweep was created")

    methodology = manifest["methodology"]
    recorded_methodology = record.get("methodology", {})
    for key, value in methodology.items():
        if recorded_methodology.get(key) != value:
            raise RunnerError(f"Suite methodology changed for {key}")
    timeout_seconds = (
        config.timeout_seconds
        if config.timeout_seconds is not None
        else float(methodology["timeout_seconds"])
    )
    model = _require_nonempty_run_string(
        record.get("deployment", {}), "model", f"{sweep_id} deployment"
    )
    expected_digest = _require_nonempty_run_string(
        record.get("deployment", {}), "digest", f"{sweep_id} deployment"
    )
    expected_ollama_version = _require_nonempty_run_string(
        record.get("deployment", {}),
        "ollama_version",
        f"{sweep_id} deployment",
    )
    client = OllamaClient(config.host, timeout_seconds=timeout_seconds)
    actual_version = _require_nonempty_run_string(
        client.version(), "version", "Ollama runtime"
    )
    if actual_version != expected_ollama_version:
        raise RunnerError(
            "Ollama version changed after the sweep was created: "
            f"expected {expected_ollama_version}, got {actual_version}"
        )
    model_tag = find_model(client.list_models(), model)
    if model_tag.get("digest") != expected_digest:
        raise RunnerError("Model digest changed after the sweep was created")

    existing_cases = record.get("cases")
    if not isinstance(existing_cases, list):
        raise RunnerError("Suite sweep cases must be a list")
    by_case_id: dict[str, dict[str, Any]] = {}
    for case_record in existing_cases:
        if not isinstance(case_record, dict):
            raise RunnerError("Suite sweep contains an invalid case record")
        case_id = case_record.get("case_id")
        if not isinstance(case_id, str) or not case_id:
            raise RunnerError("Suite sweep case has no case_id")
        if case_id in by_case_id:
            raise RunnerError(f"Suite sweep contains duplicate case {case_id}")
        by_case_id[case_id] = case_record

    resume_history = record.setdefault("resume_history", [])
    if not isinstance(resume_history, list):
        raise RunnerError("Suite resume_history must be a list")
    for history in resume_history:
        if isinstance(history, dict) and history.get("status") == "running":
            history["status"] = "interrupted"
            history["interrupted_at"] = utc_now()
    history_record: dict[str, Any] = {
        "resume_id": f"resume-{datetime.now(UTC).strftime('%Y%m%dT%H%M%SZ')}-{secrets.token_hex(4)}",
        "status": "running",
        "started_at": utc_now(),
        "resumed_case_ids": [],
        "preserved_partial_case_ids": [],
        "failed_case_ids_not_retried": [],
    }
    resume_history.append(history_record)
    pending: list[tuple[dict[str, Any], dict[str, Any], dict[str, Any]]] = []
    ordered_cases: list[dict[str, Any]] = []
    for suite_case in loaded_suite["cases"]:
        entry = suite_case["entry"]
        loaded_case = suite_case["loaded_case"]
        case_id = loaded_case["case"]["case_id"]
        case_record = by_case_id.get(case_id)
        if case_record is None:
            case_record = _new_suite_case_record(entry, loaded_case)
            pending.append((entry, loaded_case, case_record))
            history_record["resumed_case_ids"].append(case_id)
        else:
            if case_record.get("position") != entry["position"]:
                raise RunnerError(f"Suite case position changed for {case_id}")
            if case_record.get("case_path") != entry["case_path"]:
                raise RunnerError(f"Suite case path changed for {case_id}")
            status = case_record.get("status")
            if status == "running":
                case_record = preserve_interrupted_suite_case(
                    case_record, entry, loaded_case
                )
                pending.append((entry, loaded_case, case_record))
                history_record["resumed_case_ids"].append(case_id)
                history_record["preserved_partial_case_ids"].append(case_id)
            elif status == "failed":
                history_record["failed_case_ids_not_retried"].append(case_id)
            elif status != "complete":
                raise RunnerError(f"Unsupported suite case status for {case_id}: {status}")
        ordered_cases.append(case_record)

    record["cases"] = ordered_cases
    record["status"] = "running"
    record["completed_at"] = None
    record["final_running_models"] = None
    _recount_suite_cases(record)
    write_json(sweep_path, record)

    for entry, loaded_case, case_record in pending:
        try:
            _execute_suite_case_pair(
                repo_root=repo_root,
                client=client,
                record=record,
                sweep_path=sweep_path,
                sweep_id=sweep_id,
                model=model,
                host=config.host,
                results_dir=config.results_dir,
                methodology=methodology,
                timeout_seconds=timeout_seconds,
                entry=entry,
                loaded_case=loaded_case,
                case_record=case_record,
            )
        except Exception as exc:
            case_record["status"] = "failed"
            case_record["error"] = {
                "type": type(exc).__name__,
                "message": str(exc),
            }
        _recount_suite_cases(record)
        write_json(sweep_path, record)

    resolved_results_dir = resolve_repo_path(repo_root, config.results_dir)
    candidate_mapping = _suite_candidate_mapping(
        record=record,
        results_dir=resolved_results_dir,
    )
    write_json(
        sweep_dir / "candidate-map.json",
        {
            "schema_version": "1.0.0",
            "private_model_mapping": candidate_mapping,
        },
    )
    final_running = running_model_names(client.list_running_models())
    for running_model in final_running:
        client.unload_model(running_model)
    record["final_running_models"] = running_model_names(client.list_running_models())
    _recount_suite_cases(record)
    record["status"] = (
        "complete" if record["failed_case_count"] == 0 else "complete_with_failures"
    )
    record["completed_at"] = utc_now()
    history_record["status"] = "complete"
    history_record["completed_at"] = record["completed_at"]
    history_record["resulting_status"] = record["status"]
    write_json(sweep_path, record)
    return suite_completion_result(record, sweep_dir)


def add_warm_repeats(
    repo_root: Path,
    *,
    comparison_dir: Path,
    model: str,
    count: int = 2,
    reason: str,
    case_path: Path = DEFAULT_CASE_PATH,
    host: str = "http://127.0.0.1:11434",
    results_dir: Path = Path("results/runs"),
    timeout_seconds: float = 600.0,
) -> dict[str, Any]:
    if count < 1:
        raise RunnerError("Warm repeat count must be at least one")
    resolved_comparison_dir = resolve_repo_path(repo_root, comparison_dir)
    comparison_path = resolved_comparison_dir / "comparison.json"
    record = load_json(comparison_path)
    if record.get("status") != "complete":
        raise RunnerError("Warm repeats require a completed comparison")

    model_records = [entry for entry in record.get("models", []) if entry.get("model") == model]
    if len(model_records) != 1:
        raise RunnerError(f"Expected exactly one comparison entry for model {model!r}")
    model_record = model_records[0]
    existing_repeats = model_record.setdefault("additional_warm", [])
    options = record["options"]
    comparison_config = ComparisonConfig(
        models=tuple(entry["model"] for entry in record["models"]),
        case_path=case_path,
        host=host,
        results_dir=results_dir,
        comparisons_dir=resolved_comparison_dir.parent,
        temperature=options["temperature"],
        seed=options["seed"],
        num_ctx=options["num_ctx"],
        num_predict=options["num_predict"],
        think=options["think"],
        keep_alive=options["keep_alive"],
        timeout_seconds=timeout_seconds,
    )

    client = OllamaClient(host, timeout_seconds=timeout_seconds)
    find_model(client.list_models(), model)
    running_before = running_model_names(client.list_running_models())
    for running_model in running_before:
        client.unload_model(running_model)
    if running_model_names(client.list_running_models()):
        raise RunnerError("Could not clear Ollama before adaptive warm preloading")
    client.preload_model(model, comparison_config.keep_alive)
    running_after_preload = running_model_names(client.list_running_models())
    if model not in running_after_preload:
        raise RunnerError(f"Ollama does not report preloaded model {model!r} as running")

    added: list[dict[str, Any]] = []
    for offset in range(count):
        iteration = 2 + len(existing_repeats)
        result = run_once(
            repo_root,
            comparison_run_config(
                comparison_config,
                model=model,
                comparison_id=record["comparison_id"],
                phase="warm",
                iteration=iteration,
            ),
        )
        compact = compact_run_result(result)
        compact["adaptive_reason"] = reason
        existing_repeats.append(compact)
        added.append(compact)
        write_json(comparison_path, record)

    adaptive = record["methodology"].setdefault("adaptive_repetitions", [])
    adaptive.append(
        {
            "model": model,
            "reason": reason,
            "requested_runs": count,
            "running_models_before_preload": running_before,
            "running_models_after_preload": running_after_preload,
            "added_run_ids": [entry["run_id"] for entry in added],
            "completed_at": utc_now(),
        }
    )
    write_json(comparison_path, record)
    return {
        "comparison_id": record["comparison_id"],
        "model": model,
        "added": added,
    }
