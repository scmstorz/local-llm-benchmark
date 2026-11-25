"""Offline audits for proposed calibration material and evidence-bound judgments.

This module performs no inference, network calls or file writes. It neither
approves nor executes a study. Semantic judgment remains a separate operation.
"""

from __future__ import annotations

import argparse
import ast
from fractions import Fraction
import hashlib
import json
from pathlib import Path
import re

from .model_profiles import condition

ROOT = Path(__file__).resolve().parents[1]
PLAN = Path("tasks/studies/practical-profile-calibration-v0.1.draft.json")


def read(root: Path, relative: str) -> tuple[Path, str]:
    path = (root / relative).resolve()
    if not path.is_relative_to(root.resolve()) or not path.is_file():
        raise ValueError("Missing or out-of-repository calibration artifact")
    return path, path.read_text(encoding="utf-8")


def expression(value: str, inputs: dict) -> Fraction:
    """Evaluate only short, exact rational arithmetic over declared integer data."""
    tree = ast.parse(value, mode="eval")
    if len(value) > 512 or len(list(ast.walk(tree))) > 100:
        raise ValueError("Oversized reference expression")

    def visit(node):
        if isinstance(node, ast.Constant) and type(node.value) is int:
            return Fraction(node.value)
        if isinstance(node, ast.Name) and type(inputs.get(node.id)) is int:
            return Fraction(inputs[node.id])
        if isinstance(node, ast.UnaryOp) and isinstance(node.op, (ast.USub, ast.UAdd)):
            result = visit(node.operand)
            return -result if isinstance(node.op, ast.USub) else result
        if isinstance(node, ast.BinOp):
            left, right = visit(node.left), visit(node.right)
            if isinstance(node.op, ast.Add):
                return left + right
            if isinstance(node.op, ast.Sub):
                return left - right
            if isinstance(node.op, ast.Mult):
                return left * right
            if isinstance(node.op, ast.Div):
                return left / right
        raise ValueError("Unsupported reference expression")

    return visit(tree.body)


def materials(root: Path, case_path: str) -> dict:
    case = json.loads(read(root, case_path)[1])
    if case.get("split") != "calibration_only" or case.get("synthetic_sources") is not True:
        raise ValueError("Expected separate synthetic calibration material")
    visible, hidden = case["candidate_artifacts"], case["judge_only_artifacts"]
    if set(visible) != {"system", "brief", "sources"} or set(hidden) != {"reference", "rubric", "instructions"}:
        raise ValueError("Unexpected calibration artifact roles")
    texts = {key: read(root, path)[1] for key, path in visible.items()}
    paths = [read(root, p)[0] for p in [*visible.values(), *hidden.values()]]
    if len(set(paths)) != len(paths):
        raise ValueError("Candidate and judge artifacts overlap")
    reference = json.loads(read(root, hidden["reference"])[1])
    rubric = json.loads(read(root, hidden["rubric"])[1])
    if reference.get("case_id") != case["case_id"] or reference.get("candidate_delivery") is not False:
        raise ValueError("Reference binding or delivery changed")
    matches = re.findall(r"^## \[([^]]+)\]([^\n]*\n.*?)(?=^## \[|\Z)", texts["sources"], re.M | re.S)
    sections = dict(matches)
    if len(matches) != len(case["source_ids"]) or len(sections) != len(matches) or set(sections) != set(case["source_ids"]):
        raise ValueError("Source IDs differ from case")
    facts = reference["facts"]
    if len({f["id"] for f in facts}) != len(facts):
        raise ValueError("Duplicate reference fact")
    normalize = lambda s: " ".join(s.split())
    for fact in facts:
        if not fact["source_ids"] or set(fact["source_ids"]) - set(sections):
            raise ValueError("Unknown reference source")
        evidence = normalize("\n".join(sections[k] for k in fact["source_ids"]))
        if not fact["supporting_spans"] or any(not span.strip() or normalize(span) not in evidence for span in fact["supporting_spans"]):
            raise ValueError("Reference evidence is absent from its cited sources")
    for calc in reference["calculations"]:
        if expression(calc["expression"], reference["inputs"]) != Fraction(calc["expected_fraction"]):
            raise ValueError("Reference calculation mismatch: " + calc["id"])
    dimensions = rubric["dimensions"]
    if len({d["id"] for d in dimensions}) != len(dimensions) or any(type(d["weight"]) is not int or d["weight"] <= 0 for d in dimensions) or sum(d["weight"] for d in dimensions) != 100:
        raise ValueError("Rubric weights must be distinct positive dimensions totaling100")
    messages = [{"role": "system", "content": texts["system"]},
                {"role": "user", "content": texts["brief"] + "\n\n" + texts["sources"]}]
    return {"case": case, "reference": reference, "rubric": rubric, "messages": messages,
            "input_utf8_bytes": sum(len(m["content"].encode()) for m in messages),
            "artifact_hashes": {p: hashlib.sha256(read(root, p)[0].read_bytes()).hexdigest()
                                for p in [case_path, *visible.values(), *hidden.values()]}}


def judgment(value: dict, answer: str, data: dict) -> dict:
    """Check structural/evidence integrity; this cannot prove semantic correctness."""
    if (value.get("schema_version") != "practical-calibration-judgment-v1"
        or value.get("case_id") != data["case"]["case_id"]
        or not isinstance(value.get("candidate_id"), str) or not value["candidate_id"]
        or value.get("answer_sha256") != hashlib.sha256(answer.encode()).hexdigest()
        or not answer.strip()):
        raise ValueError("Judgment/answer binding is invalid")
    ratings = value["dimension_ratings"]
    if set(ratings) != {d["id"] for d in data["rubric"]["dimensions"]}:
        raise ValueError("Judgment dimensions differ from rubric")
    for rating in ratings.values():
        if type(rating.get("rating")) is not int or not 0 <= rating["rating"] <= 4 or not isinstance(rating.get("rationale"), str) or not rating["rationale"].strip():
            raise ValueError("Invalid dimension rating")
        quotes = rating.get("evidence_quotes", [])
        if not isinstance(quotes, list) or any(not isinstance(q, str) or not q.strip() or q not in answer for q in quotes):
            raise ValueError("Rating quote absent from answer")
    facts = {f["id"]: f for f in data["reference"]["facts"]}
    findings = value["critical_findings"]
    if not isinstance(findings, list):
        raise ValueError("Expected critical findings array")
    for finding in findings:
        fact = facts.get(finding.get("fact_id"))
        if (fact is None or not isinstance(finding.get("answer_quote"), str)
            or not finding["answer_quote"].strip() or finding["answer_quote"] not in answer
            or not isinstance(finding.get("explanation"), str) or not finding["explanation"].strip()
            or not isinstance(finding.get("source_ids"), list) or not finding["source_ids"]
            or set(finding["source_ids"]) - set(fact["source_ids"])):
            raise ValueError("Critical finding lacks bound answer/source evidence")
    usable = value.get("usable_as_delivered")
    if type(usable) is not bool or (findings and usable) or not isinstance(value.get("overall_reason"), str) or not value["overall_reason"].strip():
        raise ValueError("Invalid usability verdict")
    score = sum(d["weight"] * ratings[d["id"]]["rating"] / 4 for d in data["rubric"]["dimensions"])
    return {"candidate_id": value["candidate_id"], "points": score,
            "critical_findings": len(findings), "usable_as_delivered": usable,
            "structural_evidence_valid": True, "semantic_correctness_proven": False}


def audit(root: Path, plan_path: str) -> dict:
    plan = json.loads(read(root, plan_path)[1])
    batch = plan["proposed_first_batch"]
    if len(set(batch["profile_ids"])) != len(batch["profile_ids"]):
        raise ValueError("Duplicate calibration profile")
    cases = [materials(root, p) for p in batch["calibration_case_paths"]]
    count = len(cases) * len(batch["profile_ids"]) * batch["repetitions_per_case_profile"]
    if count != batch["candidate_generation_requests"] or len(cases) != batch["calibration_cases"]:
        raise ValueError("Proposed request count mismatch")
    if len(set(batch["proposed_seed_set"])) != batch["repetitions_per_case_profile"]:
        raise ValueError("Seed/repetition mismatch")
    for profile_id in batch["profile_ids"]:
        for seed in batch["proposed_seed_set"]:
            condition(profile_id, num_ctx=batch["context_tokens"],
                      num_predict=batch["maximum_reasoning_and_answer_output_tokens"], seed=seed)
    budget = batch["per_request_safety_seconds"]
    if type(budget) is not int or budget <= 0 or batch["total_safety_seconds"] != count * budget or batch["additional_inference_requests"] != 0:
        raise ValueError("Explicit total/request budget or request count changed")
    expected = {(profile, path, seed) for profile in batch["profile_ids"]
                for path in batch["calibration_case_paths"] for seed in batch["proposed_seed_set"]}
    scheduled = [(block["profile_id"], obs["case"], obs["seed"])
                 for block in batch["proposed_order"] for obs in block["observations"]]
    if len(scheduled) != count or set(scheduled) != expected:
        raise ValueError("Order must contain each proposed cell exactly once")
    owner = batch["owner_review"]
    case_names = {Path(p).parent.name: p for p in batch["calibration_case_paths"]}
    human_cells = []
    for pair in owner["pairs_specification"]:
        profiles = pair["profiles"]
        if len(profiles) != 2 or len(set(profiles)) != 2 or pair["case"] not in case_names:
            raise ValueError("Invalid owner comparison pair")
        human_cells.extend((profile, case_names[pair["case"]], pair["seed"]) for profile in profiles)
    if (len(owner["pairs_specification"]) != owner["pairs"] or len(human_cells) != owner["texts"]
        or len(set(human_cells)) != len(human_cells) or set(human_cells) - expected):
        raise ValueError("Owner comparisons must select distinct planned observations")
    return {"cases": [{"case_id": d["case"]["case_id"], "reference_calculations": len(d["reference"]["calculations"]),
                       "input_utf8_bytes": d["input_utf8_bytes"], "artifact_hashes": d["artifact_hashes"]} for d in cases],
            "proposed_generation_requests": count, "model_requests_executed": 0,
            "inference_supported_by_this_module": False}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    a = commands.add_parser("audit")
    a.add_argument("--plan", default=str(PLAN))
    j = commands.add_parser("check-judgment")
    j.add_argument("--case", required=True)
    j.add_argument("--answer", type=Path, required=True)
    j.add_argument("--judgment", type=Path, required=True)
    args = parser.parse_args(argv)
    result = audit(ROOT, args.plan) if args.command == "audit" else judgment(
        json.loads(args.judgment.read_text()), args.answer.read_text(), materials(ROOT, args.case))
    print(json.dumps(result, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
