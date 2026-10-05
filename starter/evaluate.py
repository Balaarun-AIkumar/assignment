"""Independent hand-labelled policy checks, agreement, ablation, and mutations.

Gold labels are maintained only under evaluation/. No runtime classifier is
imported here: a faulty implementation cannot grade itself as correct.
"""

import argparse
import json
import re
from pathlib import Path
import sys

from contract import FIELDS, atomic_write, check_output_paths, read_jsonl, unique_rows, validate_decision, validate_ticket, write_jsonl


ROOT = Path(__file__).resolve().parent.parent
DECISION_FIELDS = ("route", "action", "priority", "escalate")


def load_decisions(path):
    return unique_rows((validate_decision(row) for row in read_jsonl(path)), path)


def load_labels(path):
    labels = unique_rows(read_jsonl(path), path)
    for row in labels.values():
        if set(row) != FIELDS | {"rule", "reason"}:
            raise ValueError(f"invalid label fields in {path}: {row.get('id')}")
        validate_decision({key: row[key] for key in FIELDS})
        if type(row["rule"]) is not int or row["rule"] not in range(1, 7) or not row["reason"]:
            raise ValueError("label must include a rule 1..6 and rationale")
    return labels


def require_ids(actual, expected, label):
    if actual.keys() != expected.keys():
        raise ValueError(f"{label}: missing={sorted(expected.keys() - actual.keys())}, "
                         f"extra={sorted(actual.keys() - expected.keys())}")


def same(old, new):
    return all(old[field] == new[field] for field in DECISION_FIELDS)


def policy_score(decisions, labels):
    require_ids(decisions, labels, "policy ID coverage")
    violations = []
    for case_id in sorted(labels):
        expected = labels[case_id]
        actual = decisions[case_id]
        if not same(actual, expected):
            violations.append({"id": case_id, "rule": expected["rule"], "reason": expected["reason"],
                               "actual": actual, "expected": {key: expected[key] for key in FIELDS},
                               "fields": [field for field in DECISION_FIELDS if actual[field] != expected[field]]})
    return {"passed": len(labels) - len(violations), "total": len(labels),
            "rate": (len(labels) - len(violations)) / len(labels), "violations": violations}


def mutation_controls(candidate, additional, labels, extra_labels, tickets=None):
    merged = {**candidate, **additional}
    gold = {**labels, **extra_labels}
    identity = {key: ({**row, "action": "reply", "escalate": False}
                      if row["action"] == "verify_identity" else dict(row)) for key, row in merged.items()}
    incident = {key: ({**row, "action": "reply", "priority": "normal", "escalate": False}
                      if row["route"] == "safety" else dict(row)) for key, row in merged.items()}
    disclosure = {key: ({**row, "action": "reply", "escalate": False}
                        if row["action"] == "refuse" else dict(row)) for key, row in merged.items()}
    controls = []
    variants = [("bypass_identity_verification", identity),
                ("suppress_security_escalation", incident), ("allow_third_party_disclosure", disclosure)]
    if tickets is not None:
        injected = {key: dict(row) for key, row in merged.items()}
        for case_id, ticket in tickets.items():
            text = ticket["subject"] + " " + ticket["body"]
            fields = dict(re.findall(r"\b(route|action|priority|escalate)\s*=\s*(\w+)", text))
            if set(fields) == set(DECISION_FIELDS) and fields["escalate"] in ("true", "false"):
                fields["escalate"] = fields["escalate"] == "true"
                injected[case_id] = validate_decision({"id": case_id, **fields}, case_id)
        variants.append(("obey_embedded_classification", injected))
    for name, rows in variants:
        for row in rows.values():
            validate_decision(row)
        score = policy_score(rows, gold)
        changed = [case_id for case_id in merged if not same(merged[case_id], rows[case_id])]
        newly_failed = [case_id for case_id in changed if same(merged[case_id], gold[case_id]) and not same(rows[case_id], gold[case_id])]
        controls.append({"name": name, "changed_ids": sorted(changed), "newly_failed_ids": sorted(newly_failed),
                         "caught": bool(newly_failed), "policy_failures": len(score["violations"]),
                         "explanation": "Mutation keeps valid JSON and changes a safety-relevant rule; the independent policy oracle must reject it."})
    return controls, identity


def ablation(path, decisions, labels):
    rows = unique_rows(read_jsonl(path), path)
    require_ids(rows, decisions, "trace ID coverage")
    raw = {}
    for case_id, row in rows.items():
        if row["final_decision"] != decisions[case_id]:
            raise ValueError(f"trace does not match submitted decisions: {case_id}")
        raw[case_id] = validate_decision(row["raw_decision"], case_id)
    return {"without_guards": policy_score(raw, labels), "with_guards": policy_score(decisions, labels),
            "changed_ids": sorted(case_id for case_id in raw if not same(raw[case_id], decisions[case_id])),
            "method": "Replay exactly the same measured raw predictions; remove only deterministic post-model guards. Input normalization and model parameters stay fixed."}, raw


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--decisions", type=Path, required=True)
    parser.add_argument("--reference", type=Path, default=ROOT / "baseline_decisions.jsonl")
    parser.add_argument("--cases", type=Path, default=ROOT / "cases.jsonl")
    parser.add_argument("--labels", type=Path, default=ROOT / "evaluation/public_labels.jsonl")
    parser.add_argument("--additional-decisions", type=Path, default=ROOT / "results/additional_decisions.jsonl")
    parser.add_argument("--additional-cases", type=Path, default=ROOT / "evaluation/additional_cases.jsonl")
    parser.add_argument("--additional-labels", type=Path, default=ROOT / "evaluation/additional_labels.jsonl")
    parser.add_argument("--trace", type=Path)
    parser.add_argument("--additional-trace", type=Path)
    parser.add_argument("--output", type=Path, default=ROOT / "results/evaluation.json")
    parser.add_argument("--text-output", type=Path, default=ROOT / "results/evaluation.txt")
    parser.add_argument("--skip-controls", action="store_true", help="Evaluate a deliberate negative control without deriving more controls")
    args = parser.parse_args()

    inputs = [args.decisions, args.reference, args.cases, args.labels, args.additional_decisions,
              args.additional_cases, args.additional_labels, args.trace, args.additional_trace]
    outputs = [args.output, args.text_output]
    if not args.skip_controls:
        outputs.extend(args.output.parent / name for name in
                       ("weakened_decisions.jsonl", "weakened_additional_decisions.jsonl"))
    if args.trace:
        outputs.append(args.output.parent / "no_guards_public.jsonl")
    if args.additional_trace:
        outputs.append(args.output.parent / "no_guards_additional.jsonl")
    try:
        check_output_paths(inputs, outputs)
    except (ValueError, OSError) as exc:
        print(f"Evaluation: FAIL; {exc}", file=sys.stderr)
        return 1

    lines = []
    try:
        candidate, reference = load_decisions(args.decisions), load_decisions(args.reference)
        tickets = unique_rows((validate_ticket(row) for row in read_jsonl(args.cases)), args.cases)
        labels = load_labels(args.labels)
        for rows, name in ((candidate, "candidate coverage"), (reference, "baseline coverage"), (labels, "gold coverage")):
            require_ids(rows, tickets, name)
        additional = load_decisions(args.additional_decisions)
        extra_labels = load_labels(args.additional_labels)
        extra_tickets = unique_rows((validate_ticket(row) for row in read_jsonl(args.additional_cases)), args.additional_cases)
        require_ids(additional, extra_tickets, "additional decisions coverage")
        require_ids(extra_labels, extra_tickets, "additional labels coverage")
        if len(extra_tickets) < 3 or tickets.keys() & extra_tickets.keys():
            raise ValueError("Need at least three independent additional cases with nonoverlapping IDs")
        disagreements = [{"id": case_id, "baseline": reference[case_id], "candidate": candidate[case_id],
                          "candidate_correct": same(candidate[case_id], labels[case_id]),
                          "baseline_correct": same(reference[case_id], labels[case_id]),
                          "reason": labels[case_id]["reason"]}
                         for case_id in sorted(reference) if not same(reference[case_id], candidate[case_id])]
        matches = len(reference) - len(disagreements)
        report = {"contract": {"passed": True, "public_ids": len(candidate), "additional_ids": len(additional)},
                  "agreement": {"matches": matches, "total": len(reference), "rate": matches / len(reference),
                                "disagreements": disagreements},
                  "candidate_policy": policy_score(candidate, labels),
                  "baseline_policy": policy_score(reference, labels),
                  "additional_policy": policy_score(additional, extra_labels)}
        controls = []
        if not args.skip_controls:
            controls, weakened = mutation_controls(candidate, additional, labels, extra_labels, {**tickets, **extra_tickets})
            report["negative_controls"] = controls
            write_jsonl(args.output.parent / "weakened_decisions.jsonl", [weakened[key] for key in candidate])
            write_jsonl(args.output.parent / "weakened_additional_decisions.jsonl", [weakened[key] for key in additional])
        for trace, rows, gold, name in ((args.trace, candidate, labels, "public"),
                                        (args.additional_trace, additional, extra_labels, "additional")):
            if trace:
                comparison, raw = ablation(trace, rows, gold)
                report.setdefault("ablation", {})[name] = comparison
                write_jsonl(args.output.parent / f"no_guards_{name}.jsonl", raw.values())
        passed = (report["candidate_policy"]["passed"] == len(candidate) and
                  report["additional_policy"]["passed"] == len(additional) and
                  all(control["caught"] for control in controls))
        report["passed"] = passed
        lines.append(f"Contract and coverage: PASS ({len(candidate)} public, {len(additional)} additional)")
        lines.append(f"Exact baseline agreement: {matches}/{len(reference)} ({matches / len(reference):.1%})")
        for item in disagreements:
            lines.append(f"{item['id']}: baseline={json.dumps(item['baseline'])} candidate={json.dumps(item['candidate'])}; {item['reason']}")
        for key in ("candidate_policy", "baseline_policy", "additional_policy"):
            score = report[key]
            lines.append(f"{key}: {score['passed']}/{score['total']} ({score['rate']:.1%})")
            for item in score["violations"]:
                lines.append(f"  {item['id']}: rule {item['rule']}; wrong {','.join(item['fields'])}; {item['reason']}")
        for control in controls:
            lines.append(f"Negative control {control['name']}: {'CAUGHT' if control['caught'] else 'MISSED'}; newly failed={','.join(control['newly_failed_ids'])}")
        for name, comparison in report.get("ablation", {}).items():
            before, after = comparison["without_guards"], comparison["with_guards"]
            lines.append(f"Ablation {name}: model-only={before['passed']}/{before['total']}; guarded={after['passed']}/{after['total']}; changed={','.join(comparison['changed_ids'])}")
        lines.append(f"Evaluation: {'PASS' if passed else 'FAIL'}")
    except (ValueError, OSError, KeyError, TypeError) as exc:
        report = {"passed": False, "contract": {"passed": False, "error": str(exc)}}
        lines.append(f"Evaluation: FAIL; {exc}")
    atomic_write(args.output, json.dumps(report, indent=2, ensure_ascii=False) + "\n")
    atomic_write(args.text_output, "\n".join(lines) + "\n")
    print("\n".join(lines))
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    sys.exit(main())
