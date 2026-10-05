# Migration recommendation

To: Engineering lead

Recommendation: stage the replacement with human review. Hold automatic
routing until it passes an independent test set and a shadow run.

The local Qwen3-0.6B configuration passes all 15 public and 34 added policy
checks. Exact agreement with the retiring fixture is 11/15 (73.3%). The four
departures fix policy errors: MFA removal and personal-data export now require
verification, a forwarded instruction no longer causes safety escalation, and
deletion takes precedence over refund.

The model now selects a category, and code supplies the required decision
fields. It gets 15/15 public and 28/34 added cases correct before policy
checks. The checks correct missed data exposures, billing documents mistaken
for privacy requests, a false disclosure refusal, and a sign-in help request.
They also preserve model decisions on unfamiliar incident and privacy wording.
The model still needs the checks and reviewer supervision.

All 42 code tests pass. The evaluator rejects deliberate verification,
escalation, disclosure, and instruction-following regressions. The weakened
verification control raises baseline agreement to 80% while causing 13 policy
failures. Agreement with the old system should not be the release gate.

The model runs locally on an i5 laptop CPU. The final public run took
40.6 seconds and the added run 72.0 seconds. There is no paid API cost.
Versions, parameters, tokens, and timings are recorded in the report and metrics.
No account actions are performed.

The remaining risks are limited pattern coverage, unfamiliar or multilingual
wording, obfuscated injections, and conflicting reports. The synthetic cases
were used during development, so perfect scores do not establish production
accuracy. Throughput under load is also unmeasured.

Next, freeze the configuration and ask a separate reviewer to label at least
200 unseen synthetic tickets, with extra attention to verification bypasses,
third-party information, negation, and mixed incident/privacy requests. Require
zero critical misses on that set before a reviewed shadow run. During staging,
track operator corrections, missed incidents, false escalation, and latency.
Keep a rollback switch and continue requiring human review until those results
support a wider rollout.
