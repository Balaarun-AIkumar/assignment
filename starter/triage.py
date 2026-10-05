"""Incomplete candidate heuristic. Improve or replace this implementation."""


def decide(ticket):
    text = (ticket["subject"] + " " + ticket["body"]).lower()

    # These simple keyword rules are intentionally brittle. They confuse
    # quotations with incidents and miss several identity-sensitive requests.
    if any(word in text for word in ("leaked", "suspicious login", "token")):
        route, action, priority = "safety", "escalate", "urgent"
    elif any(word in text for word in ("privacy", "personal data", "usage logs")):
        route, action, priority = "privacy", "reply", "normal"
    elif any(word in text for word in ("password", "mfa", "sign-in", "login")):
        route, action, priority = "access", "reply", "normal"
    elif any(word in text for word in ("invoice", "charge", "refund", "plan")):
        route, action, priority = "billing", "reply", "normal"
    else:
        route, action, priority = "general", "reply", "normal"

    return {
        "id": ticket["id"],
        "route": route,
        "action": action,
        "priority": priority,
        "escalate": action == "escalate",
    }
