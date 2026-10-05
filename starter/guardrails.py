"""Policy checks over normalized request clauses, independent of ticket IDs."""

import re
import unicodedata

from contract import validate_decision


def normalized(text):
    text = unicodedata.normalize("NFKC", text)
    # Invisible formatting can split a command or disguise a role name.
    text = "".join(character for character in text if unicodedata.category(character) != "Cf")
    return text.translate(str.maketrans({"’": "'", "‘": "'", "“": '"', "”": '"'}))


CLASSIFICATION_INSTRUCTION = re.compile(
    r"\b(?:ignore|override|disregard)\b.{0,45}\b(?:rules|policy|instructions)\b|"
    r"\b(?:output|return|classify|set|respond|reply)\b.{0,30}"
    r"(?:route\s*[=:]|action\s*[=:]|category\s*[=:]|\{)|"
    r"\b(?:classify|mark|label|categorize|route)\b.{0,45}\b(?:as|to|into)\s+"
    r"(?:the\s+)?(?:safety|access|privacy|billing|general|security_incident|third_party_data|"
    r"privacy_request|privacy_question|account_change|login_help)\b",
    re.I,
)


def clauses(text):
    return [part.strip() for part in re.split(
        r"(?<=[.!?;])\s+|\n|\s+\b(?:but|however|separately)\b\s*,?\s*", text, flags=re.I) if part.strip()]


def prepare_ticket(ticket):
    reasons = []
    result = dict(ticket)
    for field in ("subject", "body"):
        text = normalized(ticket[field])
        if text != ticket[field]:
            reasons.append(f"normalized text in {field}")
        # These are literal ticket characters, never trusted chat boundaries.
        text, markers = re.subn(r"<\|im_start\|>\s*(?:system|assistant|developer|user)?|"
                                r"<\|(?:im_end|endoftext)\|>", "", text, flags=re.I)
        if markers:
            reasons.append(f"removed chat-role markers in {field}")
        sentences = clauses(text)
        cleaned = []
        for sentence in sentences:
            instruction = CLASSIFICATION_INSTRUCTION.search(sentence)
            if instruction:
                reasons.append(f"removed assistant-directed instruction in {field}")
                prefix = sentence[:instruction.start()]
                prefix = re.sub(r"(?:SYSTEM|ASSISTANT|DEVELOPER)\s*:\s*$", "", prefix, flags=re.I)
                if prefix.strip():
                    cleaned.append(prefix)
                continue
            if re.search(r"\b(example|hypothetical|training|fictional|fiction|simulation)\b", sentence, re.I):
                changed = re.sub(r"(?<!\w)'[^'\n]+'|\"[^\"\n]+\"", "[quoted example omitted]", sentence)
                if changed != sentence:
                    reasons.append(f"removed explicitly framed quoted example in {field}")
                    sentence = changed
            cleaned.append(sentence)
        text = "\n".join(cleaned)
        result[field] = text
    return result, reasons


def _decision(ticket, route, action, priority="normal"):
    return {"id": ticket["id"], "route": route, "action": action,
            "priority": priority, "escalate": action == "escalate"}


def enforce(ticket, candidate):
    candidate = validate_decision(dict(candidate), ticket["id"])
    text = normalized(ticket["subject"] + ". " + ticket["body"]).lower()
    sentences = clauses(text)
    actual = []
    excluded_incident = False
    for sentence in sentences:
        if re.search(r"\b(hypothetical|example|fictional|simulation)\b|\bif\b.{0,70}\b(leak|stolen|compromise)", sentence):
            excluded_incident = True
            continue
        if re.search(r"\b(no(?! one\b)|nothing|never)\b.{0,35}\b(leak|compromis|expos)|"
                     r"\bno\s+(?:(?:actual|known|reported)\s+)?(?:unauthori[sz]ed|unrecogni[sz]ed)\s+(?:access|login|sign.?in)\b|"
                     r"\b(?:not|wasn't|isn't|never)\s+(?:actually\s+)?(?:been\s+)?(?:leaked|exposed|compromised|hacked|stolen|breached)|"
                     r"\b(?:did not|didn't|has not|hasn't)\s+(?:actually\s+)?(?:leak|expose)", sentence):
            excluded_incident = True
            continue
        unquoted = re.sub(r"(?<!\w)'[^'\n]+'|\"[^\"\n]+\"", "", sentence)
        if unquoted != sentence:
            excluded_incident = True
        actual.append(unquoted)
    incident = " ".join(actual)
    patterns = (
        r"(?:active|live).{0,35}(?:token|key|credential).{0,70}(?:public|leak|expos)",
        r"(?:token|api key|credentials?|password).{0,35}(?:leaked|exposed|stolen|posted publicly)",
        r"(?:leaked|exposed|stolen).{0,45}(?:token|api key|credentials?|customer data)",
        r"(?:account|customer data|database).{0,35}(?:compromised|hacked|exposed)",
        r"(?:unauthori[sz]ed|unrecogni[sz]ed).{0,25}(?:login|sign.?in|access)",
        r"(?:login|sign.?in).{0,70}(?:not me|not mine|didn't authori[sz]e|did not authori[sz]e)",
        r"(?:someone|attacker|stranger).{0,35}(?:using|accessing|changed).{0,35}(?:account|token|key|email)",
        r"(?:customer|customers').{0,35}(?:records|data|files).{0,45}(?:public|anyone|exposed)",
        r"\b(?:active abuse|being abused|abuse in progress)\b",
    )
    if any(re.search(pattern, part) for part in actual for pattern in patterns):
        return _decision(ticket, "safety", "escalate", "urgent"), "rule 1: actual incident evidence"

    # Keep the model's semantic incident detection when a report falls outside
    # the narrow regex vocabulary. Lower-priority keywords cannot suppress it.
    incident_hint = re.search(r"\b(?:compromis\w*|hack\w*|leak\w*|expos\w*|stolen|breach|"
                              r"unauthori[sz]\w*|unrecogni[sz]\w*|attacker|stranger|anonymous|active abuse)\b", incident)
    if candidate["route"] == "safety" and candidate["action"] == "escalate" and (incident_hint or not excluded_incident):
        return _decision(ticket, "safety", "escalate", "urgent"), "rule 1: model-detected incident"

    owner = r"(?:coworker|co-worker|colleague|manager|teammate|another (?:user|person|customer)|someone else|other user)"
    third_party = rf"\b{owner}(?:'s|s')|\b(?:logs|records|data|credentials|password|api key)\b.{{0,30}}\b(?:of|for|about|belonging to)\s+(?:my\s+)?{owner}\b"
    private = r"\b(?:logs|records|email address|private data|personal data|password|credentials|api key|token)\b"
    request = r"\b(?:send|give|share|show|provide|export|download|see|want|need|fetch|retrieve|access)\b"
    targeted_request = any(re.search(third_party, part) and re.search(private, part) and re.search(request, part)
                           and not re.search(r"\b(?:do not|don't|not asking|not requesting)\b", part) for part in sentences)
    if targeted_request:
        return _decision(ticket, "privacy", "refuse"), "rule 2: request for third-party private data"

    negated_request = r"\b(?:not requesting|not asking|do not|don't|not want|no need to)\b"
    requests = [part for part in sentences if not re.search(negated_request, part)]
    rights = r"\b(delete|deleted|deletion|erase|erased|erasure|remove|export|correct|rectify|copy|download|amend)\b"
    data = r"\b(personal[ -]data|personal information|personal records|my data|my records|data export|data deletion|information (?:you|held)|records (?:you|about)|data you hold)\b"
    rights_requests = [part for part in requests if re.search(rights, part) and re.search(data, part)
                       and re.search(request + r"|\b(?:please|i request|i would like)\b", part)]
    own_rights_request = any(re.search(r"\b(?:my|me|myself)\b", part) for part in rights_requests)
    # An own-data request can correct a false refusal caused by an incidental
    # coworker mention. Otherwise preserve the model's third-party detection.
    other_private_request = any(re.search(request, part) and re.search(private, part)
                                and part not in rights_requests for part in requests)
    if candidate["action"] == "refuse" and not (own_rights_request and not other_private_request):
        return _decision(ticket, "privacy", "refuse"), "rule 2: model-detected third-party data request"
    if rights_requests:
        return _decision(ticket, "privacy", "verify_identity"), "rule 3: personal-data rights request"

    denied_rights = any(re.search(negated_request, part) and re.search(rights, part)
                       and re.search(data, part) for part in sentences)
    billing_document_request = any(re.search(
        r"\b(?:copy|download|delete|remove)\b.{0,45}\b(?:invoices?|receipts?|billing statements?)\b", part)
        and not re.search(data, part) for part in requests)
    if candidate["route"] == "privacy" and candidate["action"] == "verify_identity" and not (denied_rights or billing_document_request):
        return dict(candidate), "rule 3: model-detected personal-data rights request"

    policy_topic = r"\b(privacy policy|retention (?:terms|periods|policy)|data protection policy)\b"
    information_request = r"\?|\b(?:what|where|how|explain|tell me|send me|show me|provide)\b"
    if any(re.search(policy_topic, part) and re.search(information_request, part) for part in requests):
        return _decision(ticket, "privacy", "reply"), "rule 3: privacy-policy information"

    mutation = r"\b(?:reset|change|update|replace|switch|disable|remove|turn off|unlock|deactivate|recover)\b"
    account = r"\b(?:password|email|e-mail|mfa|2fa|two.factor|authenticator|locked account|account.{0,15}locked|unlock.{0,15}account)\b"
    account_parts = [part for part in requests if re.search(mutation, part) and re.search(account, part)]
    def information_only(part):
        informational = re.search(r"\b(how does|what is|what are|explain|documentation|instructions|tutorial|guide|policy for)\b", part)
        direct_change = re.search(r"(?:^|\b(?:please|can you|could you|will you|i want you to|i need you to)\s+)" + mutation, part)
        return informational and not direct_change
    if any(not information_only(part) for part in account_parts):
        return _decision(ticket, "access", "verify_identity"), "rule 4: account mutation requires identity verification"
    if candidate["route"] == "access" and candidate["action"] == "verify_identity" and not account_parts:
        denied_change = any(re.search(negated_request, part) and re.search(mutation, part)
                            and re.search(account, part) for part in sentences)
        if not denied_change:
            return dict(candidate), "rule 4: model-detected account mutation"

    if re.search(r"\b(sign[ -]?in|log[ -]?in|mfa challenge|authenticator challenge)\b", text):
        return _decision(ticket, "access", "reply"), "rule 4: sign-in troubleshooting"

    if re.search(r"\b(invoices?|refunds?|chargeback|charges?|charged|payments?|subscription|plan (?:price|pricing|cost)|(?:team|monthly|annual) plan)\b", text):
        return _decision(ticket, "billing", "reply"), "rule 5: explicit billing topic"

    return validate_decision(dict(candidate), ticket["id"]), "model decision (no deterministic override)"
