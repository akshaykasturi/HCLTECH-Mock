"""Check that your API keys and model names work. Sends one tiny request to each configured provider.

Usage (from backend/):  python scripts/check_llm.py
"""
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.config import get_settings  # noqa: E402
from app.llm.base import LLMError  # noqa: E402

SCHEMA = {"type": "object", "properties": {"answer": {"type": "string"}}, "required": ["answer"]}


def main() -> None:
    s = get_settings()
    clients = []
    if s.gemini_api_key:
        from app.llm.gemini import GeminiLLM
        clients.append(GeminiLLM(s.gemini_api_key, s.gemini_model, s.llm_timeout_s,
                                 thinking_level=s.gemini_thinking_level))
        print(f"Gemini thinking level: {s.gemini_thinking_level or '(not sent)'}")
    if s.groq_api_key:
        from app.llm.groq import GroqLLM
        clients.append(GroqLLM(s.groq_api_key, s.groq_model, s.llm_timeout_s))
    if not clients:
        print("No keys found. Copy backend/.env.example to backend/.env and add GEMINI_API_KEY / GROQ_API_KEY.")
        return
    for c in clients:
        start = time.perf_counter()
        try:
            out = c.generate_json("Reply with JSON only.", 'Say "ok" in the answer field.', SCHEMA)
            print(f"OK    {c.name}  {time.perf_counter() - start:.1f}s  -> {out}")
        except LLMError as e:
            print(f"FAIL  {c.name}  {time.perf_counter() - start:.1f}s  {e}")


if __name__ == "__main__":
    main()
