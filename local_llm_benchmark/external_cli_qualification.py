"""Exercise real CLI tools with synthetic responses; never contact a model."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import re
import shlex

from .external_cli import execute, finalize, prepare
from .external_cli_sandbox import check_sandbox
from .runner import RunnerError, load_json, sha256_file, utc_now, write_json


def public_test_ran(text: str, case_path: Path) -> bool:
    """Require suite output; a shell failure or import failure is not a test."""
    if re.search(r"command not found|not permitted|permission denied|ModuleNotFoundError", text, re.I):
        return False
    if "php-payment" in str(case_path):
        return "public checks passed" in text and "not ok - " in text
    if "async-cache" in str(case_path):
        return "# tests " in text and "# fail " in text and "Subtest: " in text
    return "CollectRecordsTest" in text and "Ran " in text and "FAILED" in text


def qualify(root: Path, harness: str, case_path: Path, *, condition: str = "v0.1") -> dict:
    prepared = prepare(root, harness=harness, model="benchmark-stub", case_path=case_path,
                       condition=condition)
    run = Path(prepared["run_dir"])
    acceptance = check_sandbox(run)
    if not acceptance["passed"]:
        raise RunnerError(f"Sandbox qualification failed: {run}")
    policy = load_json(run/"policy.json")
    workspace = run/"workspace"
    target = workspace/policy["writable_paths"][0]
    original = target.read_text()
    marker = "external-cli qualification marker"
    comment = "# " if target.suffix == ".py" else "// "
    updated = original.rstrip() + "\n" + comment + marker + "\n"
    protected = workspace/next(p for p in policy["readable_paths"] if p not in policy["writable_paths"])
    protected_hash = sha256_file(protected)
    read_name = "read" if harness == "mirror" else "read_file"
    write_name = "write" if harness == "mirror" else "write_file"
    modify = (write_name, {"file_path": str(target), "content": updated}) if harness == "mirror" else (
        "edit", {"file_path": str(target), "old_string": original, "new_string": updated})
    protected_modify = (write_name, {"file_path": str(protected), "content": "must never be written\n"}) if harness == "mirror" else (
        "edit", {"file_path": str(protected), "old_string": protected.read_text(), "new_string": "must never be written\n"})
    grep_args = {"pattern": marker, "path": str(target)}
    if harness == "mirror":
        grep_args["output_mode"] = "content"
    steps = [
        (read_name, {"file_path": str(target)}),
        modify,
        ("grep", grep_args),
        ("bash", {"command": policy["public_test_command"]}),
        (read_name, {"file_path": policy["hidden_test_path"]}),
        protected_modify,
        (read_name, {"file_path": str(run/"run.json")}),
    ]
    if "scratch_directory" in policy:
        scratch = Path(policy["scratch_directory"])
        script = scratch/"native-scratch.py"
        script_text = "print('scratch file qualified')\n"
        python = load_json(run/"invocation.json")["python"]
        command = shlex.join([python, "-I", str(script)])
        steps.extend([(write_name, {"file_path": str(script), "content": script_text}),
                      ("bash", {"command": command})])

    def responder(payload, sequence):
        if sequence > len(steps):
            return {"message": {"content": "Offline tool qualification finished; the task baseline remains unsolved."}}
        name, arguments = steps[sequence-1]
        available = {t["function"]["name"] for t in payload.get("tools", [])}
        if name not in available:
            raise ValueError(f"Expected native tool {name} is missing")
        return {"message": {"content": None, "tool_calls": [
            {"id": f"qualification-{sequence}", "type": "function",
             "function": {"name": name, "arguments": json.dumps(arguments)}}]}}

    execution = execute(root, run, responder=responder)
    final_request = run/"provider-wire"/f"request-{len(steps)+1:04d}.json"
    results = {}
    if final_request.exists():
        for message in load_json(final_request).get("messages", []):
            if message.get("role") == "tool":
                results[message.get("tool_call_id")] = str(message.get("content", ""))
    def result(n):
        return results.get(f"qualification-{n}", "")
    checks = {
        "sandbox_acceptance": acceptance["passed"],
        "native_cli_finished": execution["runtime_success"],
        "all_expected_provider_requests_recorded": execution["provider_requests"] == len(steps)+1,
        "native_read_returned_source": any(line.strip() in result(1) for line in original.splitlines() if len(line.strip()) > 15),
        "native_write_changed_allowed_target": target.read_text() == updated,
        "native_grep_found_marker": comment + marker in result(3),
        "public_test_observed_baseline_failure": public_test_ran(result(4), case_path),
        "hidden_read_denied": bool(re.search(r"denied|not permitted|error|outside", result(5), re.I)),
        "protected_write_denied": sha256_file(protected) == protected_hash and bool(re.search(r"denied|not permitted|error|outside", result(6), re.I)),
        "controller_record_read_denied": bool(re.search(r"denied|not permitted|error|outside", result(7), re.I)),
        "hidden_verification_deferred": not load_json(run/"run.json")["hidden_verification_executed"],
        "no_model_requests": execution["model_requests"] == 0,
    }
    if "scratch_directory" in policy:
        checks.update(native_scratch_written=script.is_file() and script.read_text() == script_text,
                      native_scratch_script_executed="scratch file qualified" in result(9)
                      and not re.search(r"denied|not permitted|error", result(9), re.I))
        wire = json.loads((run/"provider-wire/journal.json").read_text())
        checks["all_requests_have_effective_controls"] = all(
            r.get("generation_conformant") is True and r.get("effective_settings", {}).get("think") is False
            and r.get("effective_settings", {}).get("options", {}).get("num_ctx") == 16384
            and 0 < r.get("effective_settings", {}).get("options", {}).get("num_predict", 0) <= 1600
            for r in wire)
    final = finalize(root, run)
    checks["final_integrity_passed"] = final["verification"]["integrity"]["passed"]
    checks["stub_not_mistaken_for_task_success"] = not final["verified_success"]
    proof = {"schema_version": "external-cli-offline-qualification-v0.1", "qualified_at": utc_now(),
             "harness": harness, "condition": condition, "case_path": str(case_path), "run_dir": str(run.relative_to(root)),
             "passed": all(checks.values()), "checks": checks, "model_requests": 0,
             "stub_provider_requests": execution["provider_requests"],
             "native_tool_calls_requested": len(steps), "measured_admission": False,
             "record_sha256": sha256_file(run/"run.json"),
             "provider_journal_sha256": sha256_file(run/"provider-wire/journal.json")}
    write_json(run/"offline-qualification.json", proof)
    return proof


def qualify_deadline(root: Path, harness: str, *, condition: str = "v0.1") -> dict:
    """A real native shell sleeps past a short parent deadline; no model runs."""
    case = Path("tasks/coding/dev/async-cache-coalescing/case.json")
    run = Path(prepare(root, harness=harness, model="benchmark-stub", case_path=case,
                       condition=condition)["run_dir"])
    if not check_sandbox(run)["passed"]:
        raise RunnerError("Deadline qualification requires passing OS acceptance")
    invocation = load_json(run/"invocation.json")
    command = shlex.join([invocation["python"], "-I", "-c", "import time; time.sleep(30)"])

    def responder(payload, sequence):
        if sequence == 1:
            return {"message": {"content": None, "tool_calls": [
                {"id": "deadline-sleep", "type": "function", "function": {
                    "name": "bash", "arguments": json.dumps({"command": command})}}]}}
        return {}

    result = execute(root, run, responder=responder, offline_timeout=4)
    replay_refused = False
    try:
        execute(root, run, responder=responder)
    except RunnerError:
        replay_refused = True
    final = finalize(root, run)
    checks = {
        "parent_timeout_observed": result["timed_out"],
        "not_a_success": not result["runtime_success"] and not final["verified_success"],
        "native_tool_request_recorded": result["provider_requests"] == 1,
        "process_cleanup_passed": result["process_cleanup"]["passed"],
        "owned_descendants_were_observed": result["process_cleanup"]["owned_processes_observed"] > 1,
        "replay_refused": replay_refused,
        "no_model_requests": result["model_requests"] == 0,
        "private_verification_copy": (run/"verification-workspace").is_dir(),
    }
    proof = {"schema_version": "external-cli-deadline-qualification-v0.1", "harness": harness,
             "condition": condition,
             "qualified_at": utc_now(), "run_dir": str(run.relative_to(root)),
             "passed": all(checks.values()), "checks": checks,
             "parent_timeout_seconds": 4, "model_requests": 0,
             "record_sha256": sha256_file(run/"run.json")}
    write_json(run/"deadline-qualification.json", proof)
    return proof


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--harness", choices=["mirror", "vibe"], required=True)
    parser.add_argument("--condition", choices=["v0.1", "v0.2", "v0.3"], default="v0.1")
    parser.add_argument("--case", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        result = qualify(Path.cwd(), args.harness, args.case, condition=args.condition)
        print(json.dumps(result, indent=2))
        return 0 if result["passed"] else 1
    except (RunnerError, OSError, ValueError) as exc:
        print(json.dumps({"status": "failed", "error": str(exc)}))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
