"""Google Gemini client (official google-genai SDK) returning schema-constrained JSON."""
import json

from app.llm.base import LLMError


class GeminiLLM:
    def __init__(self, api_key: str, model: str, timeout_s: float = 30.0, client=None,
                 thinking_level: str = "") -> None:
        self.model = model
        self.name = f"gemini:{model}"
        # "minimal" / "low" / "medium" / "high"; less thinking = lower latency. "" = model default
        self.thinking_level = thinking_level
        if client is None:  # tests pass a fake client; real runs build the SDK client
            from google import genai
            from google.genai import types
            client = genai.Client(api_key=api_key,
                                  http_options=types.HttpOptions(timeout=int(timeout_s * 1000)))
        self.client = client

    def generate_json(self, system: str, user: str, schema: dict) -> dict:
        from google.genai import types

        thinking = (types.ThinkingConfig(thinking_level=self.thinking_level.upper())
                    if self.thinking_level else None)  # None = field not sent at all
        try:
            response = self.client.models.generate_content(
                model=self.model,
                contents=user,
                config=types.GenerateContentConfig(
                    system_instruction=system,
                    temperature=0.1,                      # low = stick closely to the evidence
                    response_mime_type="application/json",
                    response_json_schema=schema,          # the model must return this exact shape
                    thinking_config=thinking,
                ),
            )
            return json.loads(response.text)
        except Exception as e:  # network error, quota (429), bad JSON, blocked output...
            raise LLMError(f"gemini failed: {type(e).__name__}: {str(e)[:200]}") from e
