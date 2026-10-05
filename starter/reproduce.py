"""Regenerate all measured evidence and require the weakened run to fail."""

import argparse
from pathlib import Path
import subprocess
import sys

from contract import atomic_write

ROOT = Path(__file__).resolve().parent.parent


def execute(arguments, output=None, expected=0):
    print("Running:", " ".join(arguments), flush=True)
    process = subprocess.run([sys.executable, *arguments], cwd=ROOT, capture_output=True, text=True, encoding="utf-8")
    text = process.stdout + process.stderr
    print(text, end="", flush=True)
    if output:
        atomic_write(ROOT / output, text)
    if process.returncode != expected:
        raise RuntimeError(f"Expected exit {expected}, got {process.returncode}: {arguments[0]}")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mode", choices=("local", "api"), default="local")
    args = parser.parse_args()
    execute(["-m", "unittest", "discover", "-s", "tests", "-v"], "results/tests.txt")
    execute(["starter/run.py", "--mode", args.mode, "--output", "results/decisions.jsonl"], "results/public_run.txt")
    execute(["starter/run.py", "--mode", args.mode, "--cases", "evaluation/additional_cases.jsonl",
             "--output", "results/additional_decisions.jsonl"], "results/additional_run.txt")
    execute(["starter/evaluate.py", "--decisions", "results/decisions.jsonl",
             "--trace", "results/decisions.trace.jsonl", "--additional-trace", "results/additional_decisions.trace.jsonl"])
    execute(["starter/evaluate.py", "--decisions", "results/weakened_decisions.jsonl",
             "--additional-decisions", "results/weakened_additional_decisions.jsonl", "--skip-controls",
             "--output", "results/weakened_evaluation.json", "--text-output", "results/weakened_evaluation.txt"], expected=1)
    print("All checks passed; the deliberate identity-gate regression was rejected (exit 1).")


if __name__ == "__main__":
    main()
