"""Generate validated decisions plus separate, reproducible measurement evidence."""

import argparse
from contextlib import nullcontext
import hashlib
import json
import os
from pathlib import Path
import platform
import statistics
import sys
import time

from contract import atomic_write, check_output_paths, read_jsonl, unique_rows, validate_decision, validate_ticket, write_jsonl
from guardrails import enforce, prepare_ticket


ROOT = Path(__file__).resolve().parent.parent


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mode", choices=("local", "api", "heuristic"), default="local")
    parser.add_argument("--cases", type=Path, default=ROOT / "cases.jsonl")
    parser.add_argument("--output", type=Path, default=ROOT / "results" / "decisions.jsonl")
    parser.add_argument("--ablation", choices=("none", "no-guards", "no-identity-gate"), default="none")
    args = parser.parse_args()

    outputs = (args.output, args.output.with_suffix(".trace.jsonl"), args.output.with_suffix(".metrics.json"))
    check_output_paths([args.cases], outputs)
    tickets = list(unique_rows((validate_ticket(row) for row in read_jsonl(args.cases)), args.cases).values())
    started = time.perf_counter()
    if args.mode == "local":
        from local_runtime import local_server
        context = local_server()
    else:
        context = nullcontext((None, {}))
    decisions, traces = [], []
    with context as (base_url, runtime):
        client = None
        if args.mode != "heuristic":
            from model import ModelClient
            client = ModelClient(base_url=base_url, model=runtime.get("model"), local=args.mode == "local")
        else:
            from triage import decide
            print("WARNING: heuristic is a deliberately incomplete smoke control, not the migration", file=sys.stderr)
        inference_started = time.perf_counter()
        for ticket in tickets:
            try:
                prepared, changes = prepare_ticket(ticket) if client else (ticket, [])
                raw, measurement = client.decide(prepared) if client else (decide(ticket), {})
                validate_decision(raw, ticket["id"])
                guarded, reason = enforce(prepared, raw) if client else (raw, "starter heuristic control")
                result = raw if args.ablation == "no-guards" else guarded
                if args.ablation == "no-identity-gate" and result["action"] == "verify_identity":
                    result = {**result, "action": "reply", "escalate": False}
                    reason = "deliberately weakened: bypass identity gate"
                decisions.append(validate_decision(result, ticket["id"]))
                traces.append({"id": ticket["id"], "input_changes": changes, "raw_decision": raw,
                               "guarded_decision": guarded, "final_decision": result,
                               "guard_reason": reason, **measurement})
                print(f"{ticket['id']}: {result['route']}/{result['action']} ({measurement.get('elapsed_seconds', 0):.2f}s)", flush=True)
            except Exception as exc:
                raise RuntimeError(f"ticket {ticket['id']} failed: {exc}") from exc
        inference_seconds = time.perf_counter() - inference_started
        metadata = client.metadata() if client else {"model": "starter heuristic (no model execution)"}
    usages = [row.get("usage") for row in traces]
    exposed = bool(usages) and all(isinstance(usage, dict) and
        all(type(usage.get(key)) is int for key in ("prompt_tokens", "completion_tokens")) for usage in usages)
    usage = ({key: sum(item[key] for item in usages) for key in ("prompt_tokens", "completion_tokens")} if exposed else None)
    latencies = [row["elapsed_seconds"] for row in traces if "elapsed_seconds" in row]
    metrics = {**metadata, "mode": args.mode, "ablation": args.ablation, "runtime": runtime,
               "python": sys.version.split()[0], "platform": platform.platform(),
               "logical_cpus": os.cpu_count(), "processor": platform.processor(),
               "source_sha256": {name: hashlib.sha256((ROOT / "starter" / name).read_bytes()).hexdigest()
                                 for name in ("run.py", "model.py", "guardrails.py", "contract.py", "local_runtime.py", "setup_local.py",
                                              "candidate_prompt.md", "prompt_examples.json", "local_config.json")},
               "tickets": len(tickets), "cases_sha256": hashlib.sha256(args.cases.read_bytes()).hexdigest(),
               "wall_seconds": round(time.perf_counter() - started, 3),
               "inference_seconds": round(inference_seconds, 3), "usage": usage,
               "median_ticket_seconds": round(statistics.median(latencies), 3) if latencies else None,
               "max_ticket_seconds": max(latencies) if latencies else None,
               "api_cost_usd": 0 if args.mode == "local" else None,
               "cost_note": "Local CPU inference; electricity and hardware excluded" if args.mode == "local" else
                            "Not priced: provider rates unspecified; retries may incur unreported usage",
               "overrides": sum(row["raw_decision"] != row["guarded_decision"] for row in traces)}
    write_jsonl(args.output.with_suffix(".trace.jsonl"), traces)
    atomic_write(args.output.with_suffix(".metrics.json"), json.dumps(metrics, indent=2) + "\n")
    write_jsonl(args.output, decisions)
    print(f"Wrote {len(decisions)} decisions to {args.output}; wall={metrics['wall_seconds']}s; usage={usage}", flush=True)


if __name__ == "__main__":
    main()
