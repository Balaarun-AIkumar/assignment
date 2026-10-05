# Retiring triage prompt

> You are UnderAI support triage. Read the ticket and return JSON with id,
> route, action, priority, and escalate. Routes are billing, access, privacy,
> safety, or general. Actions are reply, verify_identity, escalate, or refuse.
> Be helpful and avoid unnecessary escalation. Urgent incidents should go to
> safety. Keep the answer brief.

This prompt is deliberately less precise than `policy.md`. The frozen baseline
decisions capture what the retiring configuration did on the public tickets.
They are an exercise fixture, not live model output or evidence of a specific
commercial model's behavior.
