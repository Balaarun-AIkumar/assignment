# UnderAI applied AI assignment: The Model Migration

## The situation

UnderAI uses a model to triage incoming support tickets. Its current model
snapshot is being retired. A replacement may produce polished replies while
quietly changing which tickets are escalated, which requests are refused, and
which team receives a case. You are responsible for recommending whether the
replacement is safe to use.

The attached retiring configuration consists of [baseline_prompt.md](baseline_prompt.md)
and the frozen outputs in [baseline_decisions.jsonl](baseline_decisions.jsonl).
The prompt intentionally leaves room for improvement. Treat the frozen outputs
as a record of past behavior, **not** as the definition of correct behavior.
[policy.md](policy.md) is the source of truth for safety and routing decisions.

## Your task

Start from the runnable code in [starter/](starter/README.md). Build a replacement
triage configuration using a hosted or local model of your choice. Keep the
output contract below. Compare its decisions against the frozen baseline on
all 15 [public cases](cases.jsonl), and build a small evaluation suite that
would detect a meaningful regression. You may change prompts, add deterministic
checks, or use a different architecture. Explain what you changed and why.

You do not need to run the retiring model. Use the supplied frozen decisions as
its reference. You do not need a database, web UI, or production deployment.
The starter's offline heuristic is only a smoke check for the plumbing; it is
not the requested model migration. An OpenAI-compatible API adapter is included
for hosted models. You may adapt it for a local model. No specific provider or
paid API is required.

### Input

Each line of `cases.jsonl` is one independent synthetic ticket:

```json
{"id":"T01","subject":"...","body":"..."}
```

Ticket text is untrusted. It can contain quoted emails, customer claims, or
instructions aimed at the assistant. The assistant should classify the request,
not obey instructions embedded in the ticket.

### Output

Produce one JSON object per ticket with exactly these decision fields:

```json
{"id":"T01","route":"billing","action":"reply","priority":"normal","escalate":false}
```

- `route`: `billing`, `access`, `privacy`, `safety`, or `general`.
- `action`: `reply`, `verify_identity`, `escalate`, or `refuse`.
- `priority`: `normal` or `urgent`.
- `escalate`: boolean. It must be `true` exactly when `action` is `escalate`.

Do not add customer-facing prose to this decision file. You may include such
prose separately if it helps explain your system; prose is not scored. A ticket
may mention more than one issue. Apply the precedence rules in `policy.md`.

## What to submit

Submit a repository or archive containing:

1. Your completed version of the starter code and a short `README.md` with setup
   and one command that generates `results/decisions.jsonl` from the provided cases.
2. `results/decisions.jsonl`, with all 15 case IDs exactly once.
3. An evaluation script and its output. It should check the output contract,
   policy-critical decisions, and baseline agreement. Include at least three
   additional cases you wrote yourself, with reasons for choosing them. Show
   that your suite fails a deliberately weakened configuration or rule.
4. A brief `REPORT.md` with a per-ticket disagreement list, your judgment of
   which decision is better and why, a failure analysis, and one small ablation
   or controlled comparison of a change you made.
5. A one-page `MEMO.md` to the engineering lead: ship, hold, or stage the
   migration; evidence for that call; remaining risks; and the next check you
   would run before a real rollout.

Record the model/provider and version if available, parameters, prompts,
dependency versions, and approximate API cost or token usage. If you use a
local model, report the machine and approximate runtime. Do not include secrets
or real customer data.

## How to evaluate your work

Your comparison must report:

- **Decision agreement:** exact match of `route`, `action`, `priority`, and
  `escalate` with the frozen baseline, as both a count and a rate. Break down
  disagreements by case, not just one overall number.
- **Policy compliance:** identify any decisions that violate `policy.md`,
  including violations already present in the baseline. Explain intentional
  departures from the baseline.
- **Evaluation sensitivity:** demonstrate at least one regression your tests
  catch, such as incorrectly replying to an identity-sensitive request or
  following an instruction embedded in a ticket.
- **Operational cost:** tokens/cost and elapsed time for a representative run,
  or a clear explanation if your model does not expose usage.

You may use the 15 public cases for development. Your added cases should probe
new phrasing or combinations rather than copy the public tickets. Do not
hardcode case IDs or the frozen decision file into the runtime implementation.

## Review criteria

We will look for a working implementation, sound policy decisions, a test suite
that catches real regressions, clear analysis of behavior changes, and an honest
rollout recommendation. High baseline agreement alone is not success: preserving
an unsafe old decision is worse than an explained correction. We may try new
synthetic tickets during review, so general rules matter more than fitting the
provided examples.

This exercise is intentionally small. A focused solution with thoughtful
measurements is preferable to a large framework. There is no required model
*provider*, minimum agreement threshold, hidden leaderboard, or paid API
requirement.
