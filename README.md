# UnderAI ticket triage

This submission uses Qwen3-0.6B Q8_0 locally with llama.cpp. The model chooses a
support category; code converts it to the required decision fields and applies
the policy checks. [REPORT.md](REPORT.md) contains the comparison and test
results. [MEMO.md](MEMO.md) gives the rollout recommendation.

## Run

Use Python 3.10 or later. The measured runs used Python 3.12.14 on Windows 11.
There are no pip dependencies. From the repository root, set up the local
model and runtime once:

```bash
python starter/setup_local.py
```

This downloads about 657 MB from the official projects and checks the SHA-256
hashes. Generate all 15 public decisions with:

```bash
python starter/run.py --mode local --output results/decisions.jsonl
```

After setup, this runs offline. The temporary server listens only on loopback
and stops at the end of the run. Use `py` instead of `python` if needed.
Automatic setup supports Windows x64. On other platforms, provide the pinned
model and llama.cpp b9860 using `UNDERAI_MODEL_PATH` and `UNDERAI_LLAMA_SERVER`;
those platforms have not been tested.

## Test and reproduce

Regenerate the model runs, tests, policy checks, ablation, and weakened control:

```bash
python starter/reproduce.py
```

Check the saved decisions without another model run:

```bash
python starter/evaluate.py --decisions results/decisions.jsonl --trace results/decisions.trace.jsonl --additional-trace results/additional_decisions.trace.jsonl
```

Run the code tests separately with `python -m unittest discover -s tests -v`.
The evaluator returns 1 for invalid output or a policy failure. Disagreement
with the baseline is reported separately. The weakened identity-verification
control is supposed to fail; its output is saved under `results/`.

The 34 added tickets and the reasons for their labels are in `evaluation/`.
Results, model responses, timings, and token counts are in `results/`.
Versions and checksums are in `starter/local_config.json`; the prompt and its
examples are in `starter/candidate_prompt.md` and `starter/prompt_examples.json`.
Runtime code does not read baseline decisions or evaluation labels.

For an optional hosted run, set `UNDERAI_API_KEY`, `UNDERAI_BASE_URL`, and
`UNDERAI_MODEL`, then use `--mode api`. It requires an HTTPS chat-completions
endpoint with JSON-schema support. This path has transport tests but has not
been measured against a hosted provider.

Submit `submission.zip`. It excludes downloaded models, runtime binaries,
temporary experiments, and Python caches. The original heuristic remains
available as `--mode heuristic` for comparison.

The supplied assignment adapts Deployment.inc's [Open Problem 02](https://github.com/Deployment-inc/Deployment.inc-Hiring-Problems/blob/main/problems/OP-02-the-deprecation-notice.md),
licensed under [CC BY 4.0](https://github.com/Deployment-inc/Deployment.inc-Hiring-Problems/blob/main/LICENSE.md).
