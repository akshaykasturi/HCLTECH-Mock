"""Groq client (OpenAI-compatible HTTP API) with strict JSON-schema output. Used as the backup LLM."""
import json
import re

import httpx

from app.llm.base import LLMError

URL = "https://api.groq.com/openai/v1/chat/completions"


def strict(schema: dict) -> dict:
    """Groq strict mode needs every object to list all properties as required and forbid extra keys."""
    if schema.get("type") == "object":
        props = {k: strict(v) for k, v in schema.get("properties", {}).items()}
        return {**schema, "properties": props, "required": list(props), "additionalProperties": False}
    if schema.get("type") == "array":
        return {**schema, "items": strict(schema["items"])}
    return schema


class GroqLLM:
    def __init__(self, api_key: str, model: str, timeout_s: float = 30.0, transport=None) -> None:
        self.model = model
        self.name = f"groq:{model}"
        self.http = httpx.Client(timeout=timeout_s, transport=transport,
                                 headers={"Authorization": f"Bearer {api_key}"})

    def generate_json(self, system: str, user: str, schema: dict) -> dict:
        body = {
            "model": self.model,
            "temperature": 0.1,
            "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
            "response_format": {"type": "json_schema",
                                "json_schema": {"name": "resolution", "strict": True, "schema": strict(schema)}},
        }
        for attempt in (1, 2):
            try:
                r = self.http.post(URL, json=body)
            except httpx.HTTPError as e:  # timeout, connection error...
                raise LLMError(f"groq failed: {type(e).__name__}: {str(e)[:200]}") from e
            if r.status_code < 400:
                try:
                    return json.loads(r.json()["choices"][0]["message"]["content"])
                except Exception as e:
                    raise LLMError(f"groq failed: unreadable response: {type(e).__name__}: {str(e)[:200]}") from e
            code, message = error_details(r)
            # The model produced JSON that broke the schema: often a one-off, so the same request is tried once more.
            if code == "json_validate_failed" and attempt == 1:
                continue
            raise LLMError(f"groq failed: HTTP {r.status_code} {code}: {message}")
        raise AssertionError("unreachable")


KEY_LIKE = re.compile(r"gsk_[A-Za-z0-9]{8,}")


def error_details(r: httpx.Response) -> tuple[str, str]:
    """(code, message) from Groq's error body {"error": {"code", "message", ...}}.
    Only these two fields are used: never headers, the request, or the model's failed output."""
    try:
        err = r.json().get("error") or {}
        code = str(err.get("code") or err.get("type") or "unknown")
        message = str(err.get("message") or "")
    except Exception:  # not JSON (e.g. a proxy error page)
        code, message = "unknown", r.text
    return code, KEY_LIKE.sub("gsk_****", " ".join(message.split()))[:300]
