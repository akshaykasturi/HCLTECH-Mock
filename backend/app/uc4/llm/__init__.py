"""LLM gateway for the UC4 report: one call, several providers, checked JSON out.

Use `generate(schema, system, user, ...)` from app.uc4.llm.gateway. It never raises.
"""
from app.uc4.llm.gateway import GenerateResult, generate

__all__ = ["GenerateResult", "generate"]
