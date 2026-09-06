"""Current experiment-selection status layered over immutable model identities."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from .runner import RunnerError, load_json, resolve_repo_path


DEFAULT_CATALOG_PATH = Path("models/catalog.json")
DEFAULT_LIFECYCLE_PATH = Path("models/lifecycle.json")
LIFECYCLE_STATUSES = {
    "active_default",
    "specialist_opt_in",
    "diagnostic_only",
    "retired_from_active_cohort",
}


def load_model_lifecycle(
    repo_root: Path,
    lifecycle_path: Path = DEFAULT_LIFECYCLE_PATH,
    catalog_path: Path = DEFAULT_CATALOG_PATH,
) -> dict[str, Any]:
    """Validate current selection policy against registered model tags."""
    lifecycle = load_json(resolve_repo_path(repo_root, lifecycle_path))
    catalog = load_json(resolve_repo_path(repo_root, catalog_path))
    if lifecycle.get("schema_version") != "1.0.0":
        raise RunnerError("Unsupported model lifecycle schema version")
    if lifecycle.get("lifecycle_id") != "local-model-lifecycle-v0.1":
        raise RunnerError("Unexpected model lifecycle identity")
    entries = lifecycle.get("models")
    if not isinstance(entries, list) or not entries:
        raise RunnerError("Model lifecycle must contain model entries")

    registered = {
        deployment.get("resolved_name")
        for deployment in catalog.get("deployments", [])
        if isinstance(deployment, dict)
    }
    observed: set[str] = set()
    for position, entry in enumerate(entries, start=1):
        if not isinstance(entry, dict):
            raise RunnerError(f"Invalid model lifecycle entry at position {position}")
        model = entry.get("model")
        status = entry.get("status")
        included = entry.get("include_in_default_sweeps")
        if not isinstance(model, str) or not model:
            raise RunnerError(f"Missing lifecycle model at position {position}")
        if model in observed:
            raise RunnerError(f"Duplicate model lifecycle entry: {model}")
        if model not in registered:
            raise RunnerError(f"Lifecycle model is not registered: {model}")
        if status not in LIFECYCLE_STATUSES:
            raise RunnerError(f"Unsupported lifecycle status for {model}: {status}")
        if not isinstance(included, bool):
            raise RunnerError(f"Default-sweep selection must be Boolean for {model}")
        if included != (status == "active_default"):
            raise RunnerError(
                f"Only active_default models may enter default sweeps: {model}"
            )
        roles = entry.get("allowed_explicit_roles")
        if not isinstance(roles, list) or not roles or not all(
            isinstance(role, str) and role for role in roles
        ):
            raise RunnerError(f"Lifecycle roles are incomplete for {model}")
        if status == "retired_from_active_cohort":
            if roles != ["negative_control"]:
                raise RunnerError(
                    f"Retired model may be selected only as a negative control: {model}"
                )
            if entry.get("historical_results_retained") is not True:
                raise RunnerError(f"Retired model must retain historical results: {model}")
        observed.add(model)
    return lifecycle


def models_with_status(
    lifecycle: dict[str, Any], statuses: set[str]
) -> list[str]:
    """Return model tags in declared lifecycle order for selected statuses."""
    unknown = statuses.difference(LIFECYCLE_STATUSES)
    if unknown:
        raise RunnerError("Unknown lifecycle statuses: " + ", ".join(sorted(unknown)))
    return [
        entry["model"]
        for entry in lifecycle["models"]
        if entry["status"] in statuses
    ]


def default_sweep_models(lifecycle: dict[str, Any]) -> list[str]:
    """Return the current regular-sweep cohort."""
    return models_with_status(lifecycle, {"active_default"})


def main(argv: list[str] | None = None) -> int:
    """Print the active model selection without contacting Ollama."""
    parser = argparse.ArgumentParser(description="Show current model lifecycle selection")
    parser.add_argument(
        "--status",
        action="append",
        choices=sorted(LIFECYCLE_STATUSES),
        help="Include one lifecycle status; defaults to active_default",
    )
    args = parser.parse_args(argv)
    try:
        lifecycle = load_model_lifecycle(Path.cwd().resolve())
        statuses = set(args.status or ["active_default"])
        models = models_with_status(lifecycle, statuses)
    except (OSError, RunnerError) as exc:
        print(json.dumps({"status": "failed", "error": str(exc)}, ensure_ascii=False))
        return 1
    print(
        json.dumps(
            {
                "lifecycle_id": lifecycle["lifecycle_id"],
                "selected_statuses": sorted(statuses),
                "models": models,
            },
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
