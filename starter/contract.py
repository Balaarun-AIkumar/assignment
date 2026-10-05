"""Shared output contract for the assignment's decision JSONL."""

import json
import os
from pathlib import Path
import tempfile

ROUTES = {"billing", "access", "privacy", "safety", "general"}
ACTIONS = {"reply", "verify_identity", "escalate", "refuse"}
PRIORITIES = {"normal", "urgent"}
FIELDS = {"id", "route", "action", "priority", "escalate"}

CATEGORY_DECISIONS = {
    "security_incident": ("safety", "escalate", "urgent"),
    "third_party_data": ("privacy", "refuse", "normal"),
    "privacy_request": ("privacy", "verify_identity", "normal"),
    "privacy_question": ("privacy", "reply", "normal"),
    "account_change": ("access", "verify_identity", "normal"),
    "login_help": ("access", "reply", "normal"),
    "billing": ("billing", "reply", "normal"),
    "general": ("general", "reply", "normal"),
}


def decode_category(value, ticket_id):
    if not isinstance(value, dict) or set(value) != {"category"}:
        raise ValueError("model response must contain only category")
    category = value["category"]
    if not isinstance(category, str) or category not in CATEGORY_DECISIONS:
        raise ValueError("model returned an invalid category")
    route, action, priority = CATEGORY_DECISIONS[category]
    return validate_decision({"id": ticket_id, "route": route, "action": action,
                              "priority": priority, "escalate": action == "escalate"}, ticket_id)


def validate_decision(value, expected_id=None):
    if not isinstance(value, dict) or set(value) != FIELDS:
        raise ValueError(f"decision must have exactly these fields: {sorted(FIELDS)}")
    if not isinstance(value["id"], str) or not value["id"].strip():
        raise ValueError("id must be a nonempty string")
    if expected_id is not None and value["id"] != expected_id:
        raise ValueError(f"expected id {expected_id}, got {value['id']}")
    if not isinstance(value["route"], str) or value["route"] not in ROUTES:
        raise ValueError(f"invalid route: {value['route']}")
    if not isinstance(value["action"], str) or value["action"] not in ACTIONS:
        raise ValueError(f"invalid action: {value['action']}")
    if not isinstance(value["priority"], str) or value["priority"] not in PRIORITIES:
        raise ValueError(f"invalid priority: {value['priority']}")
    if type(value["escalate"]) is not bool:
        raise ValueError("escalate must be a boolean")
    if value["escalate"] != (value["action"] == "escalate"):
        raise ValueError("escalate must be true exactly when action is escalate")
    return value


def validate_ticket(value):
    if not isinstance(value, dict) or set(value) != {"id", "subject", "body"}:
        raise ValueError("ticket must have exactly id, subject, and body")
    if not isinstance(value["id"], str) or not value["id"].strip():
        raise ValueError("ticket id must be a nonempty string")
    if any(not isinstance(value[field], str) for field in ("subject", "body")):
        raise ValueError("subject and body must be strings")
    if len(value["subject"]) + len(value["body"]) > 12000:
        raise ValueError("ticket exceeds the 12000-character limit; manual review required")
    return value


def unique_rows(rows, label):
    result = {}
    for row in rows:
        if row["id"] in result:
            raise ValueError(f"duplicate ID {row['id']} in {label}")
        result[row["id"]] = row
    if not result:
        raise ValueError(f"{label} is empty")
    return result


def check_output_paths(inputs, outputs):
    sources = {Path(path).resolve() for path in inputs if path is not None}
    destinations = [Path(path).resolve() for path in outputs]
    if len(destinations) != len(set(destinations)):
        raise ValueError("Output paths must be distinct")
    if sources.intersection(destinations):
        raise ValueError("Output files must not overwrite the input files")


def atomic_write(path, text):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    name = None
    try:
        with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", newline="\n",
                                         dir=path.parent, suffix=".tmp", delete=False) as stream:
            name = stream.name
            stream.write(text)
        os.replace(name, path)
    finally:
        if name and os.path.exists(name):
            os.unlink(name)


def write_jsonl(path, rows):
    atomic_write(path, "".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows))


def _no_duplicate_keys(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"duplicate JSON key {key}")
        result[key] = value
    return result


def parse_json(text):
    def reject_constant(value):
        raise ValueError(f"invalid JSON constant {value}")
    return json.loads(text, object_pairs_hook=_no_duplicate_keys, parse_constant=reject_constant)


def read_jsonl(path):
    with open(path, encoding="utf-8-sig") as stream:
        for line_number, line in enumerate(stream, 1):
            if line.strip():
                try:
                    yield parse_json(line)
                except ValueError as exc:
                    raise ValueError(f"{path}:{line_number}: {exc}") from exc
