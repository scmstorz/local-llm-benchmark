"""Register exact local Ollama deployments without running inference."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from .ollama import OllamaClient
from .runner import (
    RunnerError,
    find_model,
    load_json,
    resolve_repo_path,
    safe_slug,
    write_json,
)


DEFAULT_MODEL_CATALOG_PATH = Path("models/catalog.json")
MODEL_CATALOG_SCHEMA_VERSION = "1.0.0"
MODEL_CATALOG_ID = "local-ollama-deployments-v0.1"


@dataclass(frozen=True)
class ModelRegistrationConfig:
    models: tuple[str, ...]
    catalog_path: Path = DEFAULT_MODEL_CATALOG_PATH
    host: str = "http://127.0.0.1:11434"
    timeout_seconds: float = 30.0


def _nonempty_string(value: Any, label: str) -> str:
    if not isinstance(value, str) or not value:
        raise RunnerError(f"Ollama did not provide a valid {label}")
    return value


def _normalized_capabilities(model: dict[str, Any]) -> list[str]:
    capabilities = model.get("capabilities", [])
    if capabilities is None:
        return []
    if not isinstance(capabilities, list) or not all(
        isinstance(item, str) and item for item in capabilities
    ):
        raise RunnerError("Ollama returned invalid model capabilities")
    return sorted(set(capabilities))


def _public_details(model: dict[str, Any]) -> dict[str, Any]:
    details = model.get("details") or {}
    if not isinstance(details, dict):
        raise RunnerError("Ollama returned invalid model details")
    allowed = (
        "format",
        "family",
        "families",
        "parameter_size",
        "quantization_level",
        "context_length",
        "embedding_length",
    )
    return {key: details[key] for key in allowed if key in details}


def _catalog_entry(
    *,
    requested_name: str,
    model: dict[str, Any],
    ollama_version: str,
    registered_on: str,
) -> dict[str, Any]:
    digest = _nonempty_string(model.get("digest"), "model digest")
    resolved_name = _nonempty_string(
        model.get("name") or model.get("model"), "resolved model name"
    )
    capabilities = _normalized_capabilities(model)
    completion_advertised = "completion" in capabilities
    tools_advertised = "tools" in capabilities
    return {
        "deployment_id": (
            f"{safe_slug(requested_name)}-{digest[:12]}-"
            f"ollama-{safe_slug(ollama_version)}"
        ),
        "requested_name": requested_name,
        "resolved_name": resolved_name,
        "digest": digest,
        "size_bytes": model.get("size"),
        "details": _public_details(model),
        "capabilities": capabilities,
        "runtime": {"name": "ollama", "version": ollama_version},
        "registered_on": registered_on,
        "catalog_status": "registered",
        "qualification": {
            "track_a_text": (
                "eligible" if completion_advertised else "capability_not_advertised"
            ),
            "track_a_coding": (
                "eligible" if completion_advertised else "capability_not_advertised"
            ),
            "track_b_mini": "unqualified",
            "track_b_pi": "unqualified",
            "track_b_opencode": "unqualified",
            "native_tools_advertised": tools_advertised,
        },
    }


def _empty_catalog() -> dict[str, Any]:
    return {
        "schema_version": MODEL_CATALOG_SCHEMA_VERSION,
        "catalog_id": MODEL_CATALOG_ID,
        "identity_rule": (
            "A deployment is identified by exact Ollama tag, full artifact digest "
            "and runtime version. A changed digest or runtime version is appended "
            "as a new deployment and never overwrites historical evidence."
        ),
        "separation_rule": (
            "Task-suite manifests contain tasks and settings only. The catalog "
            "contains deployments; cohorts bind deployments to a suite."
        ),
        "registration_semantics": {
            "contacts_ollama_metadata_endpoints_only": True,
            "loads_model": False,
            "runs_inference": False,
            "registration_implies_track_b_qualification": False,
        },
        "deployments": [],
    }


def register_models(
    repo_root: Path,
    config: ModelRegistrationConfig,
    *,
    client: OllamaClient | None = None,
) -> dict[str, Any]:
    """Append exact installed deployments to the tracked catalog idempotently."""
    if not config.models:
        raise RunnerError("At least one exact Ollama model name is required")
    if len(set(config.models)) != len(config.models):
        raise RunnerError("Model registration contains duplicate requested names")

    resolved_catalog = resolve_repo_path(repo_root, config.catalog_path)
    if resolved_catalog.exists():
        catalog = load_json(resolved_catalog)
    else:
        catalog = _empty_catalog()
    if catalog.get("schema_version") != MODEL_CATALOG_SCHEMA_VERSION:
        raise RunnerError("Unsupported model catalog schema version")
    if catalog.get("catalog_id") != MODEL_CATALOG_ID:
        raise RunnerError("Unexpected model catalog identity")
    deployments = catalog.get("deployments")
    if not isinstance(deployments, list):
        raise RunnerError("Model catalog must contain a deployments list")
    existing_ids = [
        item.get("deployment_id") for item in deployments if isinstance(item, dict)
    ]
    if len(existing_ids) != len(deployments) or any(
        not isinstance(item, str) or not item for item in existing_ids
    ):
        raise RunnerError("Every model catalog deployment must have an identity")
    if len(set(existing_ids)) != len(existing_ids):
        raise RunnerError("Model catalog contains duplicate deployment identities")

    ollama = client or OllamaClient(config.host, timeout_seconds=config.timeout_seconds)
    version = _nonempty_string(ollama.version().get("version"), "Ollama version")
    installed = ollama.list_models()
    registered_on = datetime.now(UTC).date().isoformat()
    added: list[dict[str, Any]] = []
    existing: list[dict[str, Any]] = []

    for requested_name in config.models:
        if not requested_name.strip():
            raise RunnerError("Model registration contains an empty name")
        tag = find_model(installed, requested_name)
        entry = _catalog_entry(
            requested_name=requested_name,
            model=tag,
            ollama_version=version,
            registered_on=registered_on,
        )
        matches = [
            item
            for item in deployments
            if isinstance(item, dict)
            and item.get("requested_name") == requested_name
            and item.get("digest") == entry["digest"]
            and item.get("runtime", {}).get("version") == version
        ]
        if matches:
            existing.append(matches[0])
            continue
        if entry["deployment_id"] in existing_ids:
            raise RunnerError(
                "Deployment identity collision for " + entry["deployment_id"]
            )
        deployments.append(entry)
        existing_ids.append(entry["deployment_id"])
        added.append(entry)

    if added or not resolved_catalog.exists():
        resolved_catalog.parent.mkdir(parents=True, exist_ok=True)
        write_json(resolved_catalog, catalog)

    return {
        "status": "complete",
        "catalog_path": str(resolved_catalog),
        "ollama_version": version,
        "requested_count": len(config.models),
        "added_count": len(added),
        "already_registered_count": len(existing),
        "added_deployment_ids": [item["deployment_id"] for item in added],
        "no_inference_performed": True,
    }
