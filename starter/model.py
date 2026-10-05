"""Measured, strict OpenAI-compatible adapter for a local or hosted model."""

import hashlib
import json
import os
from pathlib import Path
import time
from urllib.error import HTTPError, URLError
from urllib.parse import urlparse
from urllib.request import Request, build_opener, ProxyHandler, HTTPRedirectHandler

from contract import CATEGORY_DECISIONS, decode_category, parse_json
from setup_local import CONFIG

ROOT = Path(__file__).resolve().parent.parent


def category_schema():
    return {"type": "object", "additionalProperties": False, "required": ["category"],
            "properties": {"category": {"type": "string", "enum": list(CATEGORY_DECISIONS)}}}


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None  # Never forward a provider credential to a redirect target.


class ModelClient:
    def __init__(self, base_url=None, model=None, local=False):
        self.local = local
        self.base_url = base_url or os.environ.get("UNDERAI_BASE_URL", "")
        self.model = model or os.environ.get("UNDERAI_MODEL", "")
        self.key = None if local else os.environ.get("UNDERAI_API_KEY")
        if not self.base_url or not self.model or (not local and not self.key):
            raise RuntimeError("Set UNDERAI_BASE_URL, UNDERAI_MODEL, and UNDERAI_API_KEY for API mode")
        url = urlparse(self.base_url)
        loopback = url.hostname in ("127.0.0.1", "localhost", "::1")
        if url.username or url.password or url.query or url.fragment:
            raise ValueError("Base URL cannot contain credentials, query, or fragment")
        if url.scheme != "https" and not (url.scheme == "http" and loopback):
            raise ValueError("Use HTTPS for hosted models; HTTP is allowed only on loopback")
        if local and not loopback:
            raise ValueError("Local mode must use a loopback server")
        self.opener = build_opener(ProxyHandler({}), NoRedirect()) if loopback else build_opener(NoRedirect())
        self.prompt = (ROOT / "starter/candidate_prompt.md").read_text(encoding="utf-8")
        self.policy = (ROOT / "policy.md").read_text(encoding="utf-8")
        self.examples_text = (ROOT / "starter/prompt_examples.json").read_text(encoding="utf-8")
        self.examples = parse_json(self.examples_text)
        for example in self.examples:
            decode_category({"category": example["category"]}, "example")
        self.parameters = {"temperature": CONFIG["temperature"], "max_tokens": CONFIG["max_tokens"]}
        if local:
            self.parameters.update(seed=CONFIG["seed"], top_p=1, top_k=0,
                                   chat_template_kwargs={"enable_thinking": False})

    def metadata(self):
        return {"model": self.model, "provider": "local llama.cpp" if self.local else "user-configured compatible API",
                "parameters": self.parameters,
                "prompt_sha256": hashlib.sha256(self.prompt.encode()).hexdigest(),
                "examples_sha256": hashlib.sha256(self.examples_text.encode()).hexdigest(),
                "policy_sha256": hashlib.sha256(self.policy.encode()).hexdigest()}

    def decide(self, ticket):
        schema = category_schema()
        response_format = ({"type": "json_object", "schema": schema} if self.local else
                           {"type": "json_schema", "json_schema": {"name": "triage", "strict": True, "schema": schema}})
        messages = [{"role": "system", "content": self.prompt + "\n\n" + self.policy}]
        for example in self.examples:
            messages.extend([
                {"role": "user", "content": json.dumps({"subject": "Support", "body": example["body"]})},
                {"role": "assistant", "content": json.dumps({"category": example["category"]})},
            ])
        messages.append({"role": "user", "content": json.dumps(
            {"subject": ticket["subject"], "body": ticket["body"]}, ensure_ascii=False)})
        payload = {"model": self.model, **self.parameters, "response_format": response_format, "messages": messages}
        headers = {"Content-Type": "application/json"}
        if self.key:
            headers["Authorization"] = f"Bearer {self.key}"
        request = Request(self.base_url.rstrip("/") + "/chat/completions",
                          data=json.dumps(payload).encode(), headers=headers, method="POST")
        started = time.perf_counter()
        for attempt in range(3):
            try:
                with self.opener.open(request, timeout=120) as response:
                    result = parse_json(response.read().decode("utf-8"))
                break
            except HTTPError as exc:
                if attempt == 2 or exc.code not in (429, 500, 502, 503, 504):
                    raise RuntimeError(f"Model HTTP error {exc.code}; response body omitted") from None
                time.sleep(0.5 * (2 ** attempt))
            except (URLError, TimeoutError):
                raise RuntimeError("Model connection failed or timed out; no heuristic fallback") from None
        choice = result["choices"][0]
        if choice.get("finish_reason") != "stop":
            raise ValueError(f"Model did not complete normally: {choice.get('finish_reason')}")
        category = parse_json(choice["message"]["content"])
        decision = decode_category(category, ticket["id"])
        return decision, {"usage": result.get("usage"), "response_model": result.get("model"),
                          "raw_category": category["category"],
                          "system_fingerprint": result.get("system_fingerprint"),
                          "elapsed_seconds": round(time.perf_counter() - started, 4),
                          "attempts": attempt + 1, "timings": result.get("timings")}
