# Triage code

See the root [README](../README.md) for commands. `run.py` starts the model,
validates each result, applies policy checks, and writes decisions plus separate
traces and measurements.

| File | Role |
| --- | --- |
| `candidate_prompt.md` | Explicit precedence, identity, quotation, and injection instructions |
| `model.py` | Local/hosted requests, category schema, decoding, and usage |
| `prompt_examples.json` | Fixed prompt examples, separate from evaluation cases |
| `guardrails.py` | Clause handling, instruction filtering, and policy checks |
| `run.py` | Input validation, generation, atomic output, separate traces and metrics |
| `contract.py` | Strict field/type/ID/boolean validation and JSONL handling |
| `local_config.json` | Model and runtime versions, checksums, and parameters |
| `setup_local.py` | Official pinned downloads with checksum verification and safe extraction |
| `local_runtime.py` | Temporary loopback-only CPU server with process cleanup |
| `evaluate.py` | Independent policy labels, baseline audit, added cases, mutations, ablation |
| `reproduce.py` | Runs the model datasets, tests, evaluator, and weakened control |
| `triage.py` | Original heuristic, preserved as an explicitly incomplete control |

Expected labels are in `evaluation/` and are used only by the evaluator. The
classifier uses ticket text and the fixed policy. The local run needs no paid
provider or additional Python packages.
