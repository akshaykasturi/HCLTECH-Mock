"""The two ways we talk to an LLM, with the standard library only (urllib).

Each function sends one request and returns the model's raw text (it should be JSON).
On any problem it raises ProviderError with a short message that never contains a key:
we only report the HTTP status code or the kind of failure, never the response body.
"""
import json
import socket
import urllib.error
import urllib.request

GEMINI_URL = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"


class ProviderError(Exception):
    """A provider call failed. The message is short and safe to show."""


def _post_json(url: str, headers: dict[str, str], body: dict | None, timeout: float) -> dict:
    """POST body as JSON (or GET when body is None) and return the JSON reply."""
    data = None if body is None else json.dumps(body).encode("utf-8")
    request = urllib.request.Request(url, data=data, method="GET" if body is None else "POST",
                                     headers={"Content-Type": "application/json",
                                              # urllib's default "Python-urllib/x" is blocked by
                                              # some providers' firewalls (Groq answers 403)
                                              "User-Agent": "uc4-diagnosis/1.0", **headers})
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        raise ProviderError(f"HTTP {exc.code}") from None
    except (TimeoutError, socket.timeout):
        raise ProviderError("timeout") from None
    except urllib.error.URLError as exc:
        reason = "timeout" if isinstance(exc.reason, (TimeoutError, socket.timeout)) else "connection failed"
        raise ProviderError(reason) from None
    except (json.JSONDecodeError, UnicodeDecodeError):
        raise ProviderError("response was not JSON") from None


def gemini(system: str, user: str, model: str, key: str, timeout: float) -> str:
    """Google Gemini. The key goes in the x-goog-api-key header, never in the URL."""
    body = {
        "systemInstruction": {"parts": [{"text": system}]},
        "contents": [{"role": "user", "parts": [{"text": user}]}],
        "generationConfig": {"responseMimeType": "application/json", "temperature": 0},
    }
    reply = _post_json(GEMINI_URL.format(model=model), {"x-goog-api-key": key}, body, timeout)
    try:
        return reply["candidates"][0]["content"]["parts"][0]["text"]
    except (KeyError, IndexError, TypeError):
        raise ProviderError("unexpected response shape") from None


def openai_compat(system: str, user: str, base_url: str, model: str, key: str, timeout: float) -> str:
    """Any OpenAI-compatible chat API: Groq, or Ollama at http://127.0.0.1:11434/v1 (no key)."""
    body = {
        "model": model,
        "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
        "response_format": {"type": "json_object"},
        "temperature": 0,
    }
    headers = {"Authorization": f"Bearer {key}"} if key else {}
    reply = _post_json(f"{base_url.rstrip('/')}/chat/completions", headers, body, timeout)
    try:
        return reply["choices"][0]["message"]["content"]
    except (KeyError, IndexError, TypeError):
        raise ProviderError("unexpected response shape") from None


# ---- which models can this key use? (scripts/check_llm.py --models) ------------------------

def gemini_models(key: str, timeout: float) -> list[str]:
    """Gemini model names this key can call with generateContent (key in the header)."""
    url = "https://generativelanguage.googleapis.com/v1beta/models?pageSize=1000"
    reply = _post_json(url, {"x-goog-api-key": key}, None, timeout)
    try:
        return sorted(m["name"].removeprefix("models/") for m in reply.get("models", [])
                      if "generateContent" in m.get("supportedGenerationMethods", []))
    except (KeyError, TypeError, AttributeError):
        raise ProviderError("unexpected response shape") from None


def openai_compat_models(base_url: str, key: str, timeout: float) -> list[str]:
    """Model ids an OpenAI-compatible server offers (GET {base_url}/models)."""
    headers = {"Authorization": f"Bearer {key}"} if key else {}
    reply = _post_json(f"{base_url.rstrip('/')}/models", headers, None, timeout)
    try:
        return sorted(m["id"] for m in reply.get("data", []))
    except (KeyError, TypeError, AttributeError):
        raise ProviderError("unexpected response shape") from None
