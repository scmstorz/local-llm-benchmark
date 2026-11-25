"""Source-bound execution of the approved twenty-answer calibration pilot.

The parent owns a hard watchdog and a separate worker process group per answer.
Workers forward exactly one native request, retain both wire representations,
and never execute candidate text. Historical benchmark runners are unchanged.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import secrets
import signal
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.request

from .external_cli_native import NativeResponse
from .external_cli import _process_snapshot as process_ownership
from .external_cli_provider import _NoRedirect
from .log_incident_smokes import (
    ResourceGatePause, _blocking_processes, _process_snapshot, run_resource_gate,
)
from .model_profiles import binding_sha256, condition, validate_deployment
from .ollama import OllamaClient
from .practical_calibration import ROOT, PLAN, audit, materials
from .profiled_native import native_request
from .runner import load_json, sha256_file, utc_now

UPSTREAM = "http://127.0.0.1:11434"


def save(path: Path, value: dict):
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_name(path.name + ".tmp")
    with temp.open("w") as out:
        json.dump(value, out, ensure_ascii=False, indent=2)
        out.write("\n")
        out.flush()
        os.fsync(out.fileno())
    temp.replace(path)


def once(path: Path, value: dict):
    with path.open("x") as out:
        json.dump(value, out, ensure_ascii=False, indent=2)
        out.write("\n")


class LocalClient(OllamaClient):
    """All metadata/cleanup requests stay on the fixed local, non-proxied host."""

    def __init__(self, timeout_seconds=5):
        super().__init__(UPSTREAM, timeout_seconds)
        self.opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), _NoRedirect())

    def _request_json(self, method, path, payload=None):
        request = urllib.request.Request(
            UPSTREAM + path, json.dumps(payload).encode() if payload is not None else None,
            {"Content-Type": "application/json"}, method=method,
        )
        with self.opener.open(request, timeout=self.timeout_seconds) as response:
            result = json.load(response)
        if not isinstance(result, dict) or result.get("error"):
            raise ValueError("Invalid local metadata/cleanup response")
        return result


def stop_group(process: subprocess.Popen):
    """Signal only live members of our private group, bound to OS start metadata."""
    before = process_ownership()
    owned = {pid: row for pid, row in before.items()
             if (pid == process.pid or row["group"] == process.pid) and "Z" not in row["state"]}
    if not owned:
        return {"observed": 0, "remaining": []}
    for pid in sorted(owned, reverse=True):
        try:
            os.kill(pid, signal.SIGTERM)
        except ProcessLookupError:
            pass
    time.sleep(0.25)
    current = process_ownership()
    for pid, old in owned.items():
        row = current.get(pid)
        if row and row["start"] == old["start"] and "Z" not in row["state"]:
            try:
                os.kill(pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
    process.wait(timeout=5)
    after = process_ownership()
    remaining = [pid for pid, old in owned.items() if pid in after
                 and after[pid]["start"] == old["start"] and "Z" not in after[pid]["state"]]
    if remaining:
        raise RuntimeError("Owned worker processes remain after cleanup")
    return {"observed": len(owned), "remaining": remaining}


def bounded_process(argv: list[str], directory: Path, seconds: float, monitor=None) -> dict:
    if not isinstance(seconds, (int, float)) or isinstance(seconds, bool) or not 0 < seconds <= 1800:
        raise ValueError("A finite approved worker deadline is required")
    started = time.monotonic()
    record = {"started_at": utc_now(), "budget_seconds": seconds, "timed_out": False,
              "monitor_error": None, "cleanup_finished": False}
    with (directory/"worker.stdout").open("wb") as stdout, (directory/"worker.stderr").open("wb") as stderr:
        process = subprocess.Popen(argv, cwd=ROOT, stdout=stdout, stderr=stderr, start_new_session=True)
        record["owned_process_group"] = process.pid

        def expire():
            if process.poll() is None:
                record.update(timed_out=True, deadline_signal_elapsed_seconds=time.monotonic()-started)
                record["deadline_cleanup"] = stop_group(process)

        timer = threading.Timer(max(0.001, seconds-(time.monotonic()-started)), expire)
        timer.start()
        next_monitor = started
        try:
            while process.poll() is None:
                if monitor and time.monotonic() >= next_monitor:
                    try:
                        monitor()
                    except Exception as exc:
                        record["monitor_error"] = {"type": type(exc).__name__, "message": str(exc)}
                        stop_group(process)
                        break
                    next_monitor = time.monotonic()+5
                try:
                    process.wait(timeout=0.25)
                except subprocess.TimeoutExpired:
                    pass
        finally:
            timer.cancel()
            timer.join()
            record["final_cleanup"] = stop_group(process)
            process.wait(timeout=5)
        record.update(returncode=process.returncode, elapsed_seconds=time.monotonic()-started,
                      cleanup_finished=True, finished_at=utc_now())
    save(directory/"watchdog.json", record)
    return record


def collect(response, converter: NativeResponse, sink, heartbeat=None):
    """Capture chunks before parsing, so a killed worker retains partial framing."""
    pending = b""
    terminal = None
    while chunk := response.read1(65536):
        sink.write(chunk)
        sink.flush()
        pending += chunk
        while b"\n" in pending:
            line, pending = pending.split(b"\n", 1)
            if len(line) > 8*1024*1024:
                raise ValueError("Oversized native event")
            if not line.strip():
                continue
            item = json.loads(line)
            if item.get("error"):
                raise RuntimeError("Native backend error: " + str(item["error"]))
            converter.feed(item)
            if item.get("done"):
                terminal = item
        if len(pending) > 8*1024*1024:
            raise ValueError("Oversized partial native event")
        if heartbeat:
            heartbeat()
    if pending.strip():
        raise ValueError("Incomplete native NDJSON event")
    converter.finish()
    return terminal


def worker(spec_path: Path) -> int:
    spec = load_json(spec_path)
    directory = spec_path.parent
    c, payload = spec["condition"], spec["request"]
    expected = c["candidate"]
    client = LocalClient()
    result = {"started_at": utc_now(), "forwarded": False, "status": "admission",
              "condition_sha256": binding_sha256(c)}
    converter = NativeResponse(payload, 1)
    started = time.monotonic()
    try:
        native, profile_audit = native_request(payload, c)
        save(directory/"request.original.json", payload)
        save(directory/"request.native.json", native)
        save(directory/"profile-audit.json", profile_audit)
        runtime = client.version()
        tag = next((m for m in client.list_models()["models"] if m["name"] == expected["model"]), {})
        show = client.show_model(expected["model"])
        save(directory/"deployment-metadata.json", {"runtime": runtime, "tag": tag, "show": show})
        admission = validate_deployment(c, tag=tag, show=show, runtime=runtime)
        save(directory/"deployment-admission.json", admission)
        result["before_ps"] = client.list_running_models()
        if any(m["name"] != expected["model"] for m in result["before_ps"].get("models", [])):
            raise ValueError("Unexpected loaded model before generation")
        result.update(forwarded=True, status="generating", request_started_at=utc_now())
        save(directory/"worker-progress.json", result)
        request = urllib.request.Request(UPSTREAM+"/api/chat", json.dumps(native).encode(),
                                         {"Content-Type": "application/json"})
        last_heartbeat = time.monotonic()

        def heartbeat():
            nonlocal last_heartbeat
            if time.monotonic()-last_heartbeat >= 5:
                save(directory/"worker-progress.json", {**result, "observed_at": utc_now(),
                     "thinking_characters": converter.thinking_characters,
                     "content_characters": len(converter.message.get("content", ""))})
                last_heartbeat = time.monotonic()

        # The independent parent deadline, not a300-second socket default, limits this request.
        with client.opener.open(request, timeout=spec["budget_seconds"]+10) as response:
            with (directory/"response.native.ndjson").open("wb", buffering=0) as sink:
                terminal = collect(response, converter, sink, heartbeat)
        converted = converter.finish()
        (directory/"response.original.json").write_bytes(converted)
        result["after_ps"] = client.list_running_models()
        contexts = [m.get("context_length") for m in result["after_ps"].get("models", [])
                    if m["name"] == expected["model"] and m.get("digest") == expected["model_digest"]]
        reserve = c["limits"]["num_ctx"]-converter.usage["prompt_tokens"]-c["limits"]["num_predict"]
        result.update(status="complete", finish_reason=converter.finish_reason,
                      usage=converter.usage, observed_contexts=contexts,
                      observed_thinking_characters=converter.thinking_characters,
                      generation_conformant=converter.usage["completion_tokens"] <= c["limits"]["num_predict"],
                      output_reserve_margin_tokens=reserve, output_reserve_fits=reserve >= 0,
                      context_conformant=contexts == [c["limits"]["num_ctx"]],
                      backend_durations={k: v for k, v in terminal.items() if k.endswith("_duration")})
    except Exception as exc:
        result.update(status="error", error={"type": type(exc).__name__, "message": str(exc)})
    finally:
        save(directory/"partial-message.json", converter.message)
        (directory/"answer.md").write_text(converter.message.get("content", ""), encoding="utf-8")
        result.update(finished_at=utc_now(), worker_wall_seconds=time.monotonic()-started)
        save(directory/"worker-result.json", result)
    return 0 if result["status"] == "complete" else 1


def files(directory: Path) -> dict:
    return {str(p.relative_to(directory)): sha256_file(p) for p in sorted(directory.rglob("*")) if p.is_file()}


def check_sources(plan: dict):
    if subprocess.check_output(["git", "status", "--porcelain"], cwd=ROOT, text=True).strip():
        raise ValueError("Execution source tree must stay clean")
    if subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip() != plan["source_commit"]:
        raise ValueError("Execution source commit drift")
    for path, expected in plan["source_hashes"].items():
        if sha256_file(ROOT/path) != expected:
            raise ValueError("Execution artifact drift: " + path)


def prepare(study: Path, gate_source: Path) -> dict:
    study = study.resolve()
    if not study.is_relative_to(ROOT/"results"):
        raise ValueError("Private study must be below repository results")
    if (study/"plan.json").exists():
        raise ValueError("A frozen study already exists")
    draft = load_json(ROOT/PLAN)
    if not all(draft["authorization"].get(k) is True for k in
               ["live_execution_authorized", "concrete_case_scope_agreed", "numeric_budgets_agreed", "run_counts_agreed"]):
        raise ValueError("Explicit approved pilot execution is required")
    audit(ROOT, str(PLAN))
    batch = draft["proposed_first_batch"]
    source_paths = {str(PLAN), "docs/practical-profile-calibration-v0.1.md",
                    "models/practical-profiles-v0.1.json"}
    source_paths.update(str(p.relative_to(ROOT)) for p in (ROOT/"local_llm_benchmark").glob("*.py"))
    source_paths.update({"tests/test_practical_calibration.py", "tests/test_calibration_run.py"})
    data = {path: materials(ROOT, path) for path in batch["calibration_case_paths"]}
    for path, item in data.items():
        source_paths.update(item["artifact_hashes"])
    plan = {"schema_version": "practical-calibration-live-v1", "created_at": utc_now(),
            "source_commit": subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip(),
            "source_hashes": {p: sha256_file(ROOT/p) for p in sorted(source_paths)},
            "authorization": draft["live_execution_confirmation"],
            "maximum_generation_requests": batch["candidate_generation_requests"],
            "budget_seconds": batch["per_request_safety_seconds"],
            "maximum_active_seconds": batch["total_safety_seconds"],
            "resource_gate": load_json(gate_source)["resource_gate"], "blocks": [],
            "no_retries": True, "extra_generations": 0}
    for block in batch["proposed_order"]:
        units = []
        for observation in block["observations"]:
            item = data[observation["case"]]
            c = condition(block["profile_id"], num_ctx=batch["context_tokens"],
                          num_predict=batch["maximum_reasoning_and_answer_output_tokens"], seed=observation["seed"])
            uid = f"u{sum(len(b['units']) for b in plan['blocks'])+len(units)+1:02d}"
            units.append({"unit_id": uid, "candidate_id": "T-"+secrets.token_hex(6),
                          "profile_id": block["profile_id"], "case_path": observation["case"],
                          "case_id": item["case"]["case_id"], "seed": observation["seed"],
                          "condition": c, "condition_sha256": binding_sha256(c),
                          "request": {"model": c["candidate"]["model"], "stream": False, "messages": item["messages"]}})
        plan["blocks"].append({"profile_id": block["profile_id"], "units": units})
    units = [u for b in plan["blocks"] for u in b["units"]]
    if len(units) != plan["maximum_generation_requests"] or len(units) != 20:
        raise ValueError("Exact twenty-request scope changed")
    layout = {"created_at": utc_now(), "pairs": []}
    for i, pair in enumerate(batch["owner_review"]["pairs_specification"], 1):
        selected = [next(u for u in units if u["profile_id"] == p and u["seed"] == pair["seed"]
                         and Path(u["case_path"]).parent.name == pair["case"]) for p in pair["profiles"]]
        if secrets.randbelow(2):
            selected.reverse()
        layout["pairs"].append({"pair_id": f"P{i}", "case_path": selected[0]["case_path"],
                                "sides": {label: u["unit_id"] for label, u in zip(["A", "B"], selected)}})
    check_sources(plan)
    study.mkdir(parents=True, exist_ok=True)
    for path, item in data.items():
        directory = study/"judge-materials"/Path(path).parent.name
        directory.mkdir(parents=True, exist_ok=False)
        for role, original in {**item["case"]["candidate_artifacts"], **item["case"]["judge_only_artifacts"]}.items():
            (directory/Path(original).name).write_bytes((ROOT/original).read_bytes())
    once(study/"owner-layout.private.json", layout)
    plan["owner_layout_sha256"] = sha256_file(study/"owner-layout.private.json")
    plan["judge_material_hashes"] = files(study/"judge-materials")
    once(study/"plan.json", plan)
    return {"study": str(study), "source_commit": plan["source_commit"],
            "plan_sha256": sha256_file(study/"plan.json"), "generation_requests": 20}


def activity(client: LocalClient, model: str, rules: list[dict], tolerate_transport=False) -> dict:
    blocked = _blocking_processes(rules, _process_snapshot())
    if blocked:
        raise ValueError("Competing workload or unexpected model activity")
    try:
        ps = client.list_running_models()
    except (OSError, urllib.error.URLError) as exc:
        if not tolerate_transport:
            raise
        return {"observed_at": utc_now(), "metadata_transport_unavailable": type(exc).__name__,
                "blocking_processes": []}
    if any(m["name"] != model for m in ps.get("models", [])):
        raise ValueError("Competing workload or unexpected model activity")
    return {"observed_at": utc_now(), "running": ps, "blocking_processes": blocked}


def recover(directory: Path, payload: dict) -> dict:
    converter = NativeResponse(payload, 1)
    path = directory/"response.native.ndjson"
    if path.exists():
        for raw in path.read_bytes().splitlines(keepends=True):
            if not raw.endswith(b"\n"):
                break
            try:
                converter.feed(json.loads(raw))
            except (ValueError, KeyError, TypeError):
                break
    (directory/"answer.md").write_text(converter.message.get("content", ""))
    save(directory/"recovered-message.json", converter.message)
    return converter.message


def run(study: Path) -> dict:
    study = study.resolve()
    plan = load_json(study/"plan.json")
    check_sources(plan)
    if sha256_file(study/"owner-layout.private.json") != plan["owner_layout_sha256"] or files(study/"judge-materials") != plan["judge_material_hashes"]:
        raise ValueError("Evaluation material/layout drift")
    once(study/"consumed.json", {"started_at": utc_now(), "plan_sha256": sha256_file(study/"plan.json")})
    state = {"schema_version": "practical-calibration-execution-v1", "started_at": utc_now(),
             "plan_sha256": sha256_file(study/"plan.json"), "source_commit": plan["source_commit"],
             "units": [], "gates": [], "postflights": [], "status": "running", "model_requests": 0}
    client = LocalClient()
    active_seconds = 0.0
    try:
        for block in plan["blocks"]:
            check_sources(plan)
            first = block["units"][0]["condition"]["candidate"]
            model = first["model"]
            print(json.dumps({"stage": "resource_gate", "profile": block["profile_id"], "at": utc_now()}), flush=True)
            gate = run_resource_gate({"resource_gate": plan["resource_gate"],
                                      "runtime": {"version": first["ollama_version"]},
                                      "deployment": {"name": model, "digest": first["model_digest"]}}, client=client)
            state["gates"].append(gate)
            try:
                for unit in block["units"]:
                    check_sources(plan)
                    before = activity(client, model, plan["resource_gate"]["blocking_process_rules"])
                    if active_seconds+plan["budget_seconds"] > plan["maximum_active_seconds"]:
                        raise ValueError("Total approved active-generation budget exhausted")
                    directory = study/"units"/unit["unit_id"]
                    directory.mkdir(parents=True, exist_ok=False)
                    spec = {"condition": unit["condition"], "request": unit["request"],
                            "budget_seconds": plan["budget_seconds"]}
                    once(directory/"worker-spec.json", spec)
                    once(directory/"started.json", {"started_at": utc_now(), "before": before})
                    print(json.dumps({"stage": "answer", "unit": unit["unit_id"], "profile": unit["profile_id"],
                                      "case": unit["case_id"], "seed": unit["seed"], "at": utc_now()}), flush=True)
                    def monitor():
                        observation = activity(client, model, plan["resource_gate"]["blocking_process_rules"], tolerate_transport=True)
                        with (directory/"resource-monitor.jsonl").open("a") as out:
                            out.write(json.dumps(observation)+"\n")

                    watch = bounded_process([sys.executable, "-m", "local_llm_benchmark.calibration_run", "worker", str(directory/"worker-spec.json")],
                                            directory, plan["budget_seconds"], monitor)
                    active_seconds += min(watch["elapsed_seconds"], plan["budget_seconds"])
                    outcome = load_json(directory/"worker-result.json") if (directory/"worker-result.json").exists() else {}
                    message = recover(directory, unit["request"])
                    progress = load_json(directory/"worker-progress.json") if (directory/"worker-progress.json").exists() else {}
                    forwarded = bool(outcome.get("forwarded") or progress.get("forwarded"))
                    state["model_requests"] += int(forwarded)
                    technical = (not watch["timed_out"] and not watch["monitor_error"]
                                 and watch["returncode"] == 0 and outcome.get("status") == "complete"
                                 and outcome.get("generation_conformant") is True
                                 and outcome.get("context_conformant") is True and outcome.get("output_reserve_fits") is True
                                 and outcome.get("finish_reason") == "stop" and bool(message.get("content", "").strip())
                                 and not message.get("tool_calls"))
                    record = {"unit_id": unit["unit_id"], "candidate_id": unit["candidate_id"],
                              "profile_id": unit["profile_id"], "case_id": unit["case_id"], "seed": unit["seed"],
                              "condition_sha256": unit["condition_sha256"], "forwarded": forwarded,
                              "technical_ok": technical, "watchdog": watch, "worker": outcome,
                              "word_count": len(re.findall(r"\b\w+(?:[-’']\w+)*\b", message.get("content", ""))),
                              "answer_sha256": sha256_file(directory/"answer.md"),
                              "files": files(directory)}
                    once(directory/"record.json", record)
                    state["units"].append(record)
                    save(study/"progress.json", state)
                    print(json.dumps({"unit": unit["unit_id"], "technical_ok": technical,
                                      "seconds": round(watch["elapsed_seconds"], 2), "words": record["word_count"],
                                      "finish_reason": outcome.get("finish_reason"), "error": outcome.get("error")}), flush=True)
                    if watch["timed_out"]:
                        # Free only this admitted model; the failed unit is never repeated.
                        client.unload_model(model)
                    if watch["monitor_error"]:
                        raise ValueError("Resource monitor paused the study during a consumed answer")
                    if outcome.get("status") == "complete" and not outcome.get("context_conformant"):
                        raise ValueError("Observed runtime context differs from the approved condition")
            finally:
                ps = client.list_running_models()
                if any(m["name"] == model for m in ps.get("models", [])):
                    LocalClient(timeout_seconds=30).unload_model(model)
                ps = client.list_running_models()
                state["postflights"].append({"profile_id": block["profile_id"], "at": utc_now(), "running": ps})
                save(study/"progress.json", state)
                if ps.get("models"):
                    raise ValueError("Nonempty block postflight; do not continue")
        state["status"] = "complete"
    except Exception as exc:
        state.update(status="paused", error={"type": type(exc).__name__, "message": str(exc)})
        if isinstance(exc, ResourceGatePause):
            state["resource_gate_evidence"] = exc.evidence
    state.update(finished_at=utc_now(), active_worker_seconds=active_seconds,
                 completed_units=len(state["units"]), technical_successes=sum(u["technical_ok"] for u in state["units"]))
    save(study/"execution-closeout.json", state)
    return state


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    p = commands.add_parser("prepare")
    p.add_argument("study", type=Path)
    p.add_argument("--gate-source", type=Path, required=True)
    r = commands.add_parser("run")
    r.add_argument("study", type=Path)
    w = commands.add_parser("worker")
    w.add_argument("spec", type=Path)
    args = parser.parse_args(argv)
    if args.command == "worker":
        return worker(args.spec)
    result = prepare(args.study, args.gate_source) if args.command == "prepare" else run(args.study)
    print(json.dumps({k: v for k, v in result.items() if k not in {"units", "gates", "postflights"}}, ensure_ascii=False, indent=2))
    return 0 if args.command == "prepare" or result["status"] == "complete" else 1


if __name__ == "__main__":
    raise SystemExit(main())
