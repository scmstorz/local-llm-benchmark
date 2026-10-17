"""Coverage 0.3 adds native direct-coding completion without changing a run."""
from __future__ import annotations

import argparse
from collections import Counter
from datetime import datetime
import json
from pathlib import Path
from typing import Any

from . import core_records as previous
from .runner import RunnerError, load_json

VERSION = "0.3.0"


def _native_direct_complete(record: dict[str, Any]) -> bool:
    """Recognize the actual terminal record emitted by coding.run_track_a_once."""
    if (record.get("track") != "A"
            or record.get("harness", {}).get("name") not in {
                "local_llm_benchmark.direct_patch", "local_llm_benchmark.direct_files"}
            or record.get("execution", {}).get("execution_status") != "completed"
            or record.get("verification_execution", {}).get("mode") != "immediate"
            or not isinstance(record.get("outcome", {}).get("verified_success"), bool)):
        return False
    try:
        values = [datetime.fromisoformat(value.replace("Z", "+00:00")) for value in (
            record["started_at"], record["verification_execution"]["completed_at"], record["completed_at"])]
    except (KeyError, TypeError, ValueError, AttributeError):
        return False
    return all(value.tzinfo is not None for value in values) and values[0] <= values[1] and values[0] <= values[2]


def coverage(root: Path, plan_path: Path, admission_study: Path | None = None) -> dict[str, Any]:
    result = previous.coverage(root, plan_path, admission_study)
    result["coverage_version"] = VERSION
    if not result["source_drift"]:
        for row in result["cells"]:
            if (row["system"] != "direct-coding" or row["status"] != "in_progress"
                    or not row.get("evidence")):
                continue
            record = load_json(root / row["evidence"]["path"])
            if _native_direct_complete(record):
                row.update(status="complete", completion_basis="native_direct_execution_and_immediate_verification")
    result["counts"] = dict(Counter(row["status"] for row in result["cells"]))
    return result


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--plan", type=Path, required=True)
    parser.add_argument("--admission-study", type=Path)
    args = parser.parse_args(argv)
    try:
        result = coverage(Path.cwd().resolve(), args.plan, args.admission_study)
    except RunnerError as exc:
        parser.exit(1, str(exc) + "\n")
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
