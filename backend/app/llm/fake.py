"""Scripted LLM for tests only. Returns whatever response it was given; records the prompts it saw."""


class FakeLLM:
    name = "fake"

    def __init__(self, response: dict | None = None, fail: bool = False) -> None:
        self.response = response
        self.fail = fail
        self.calls: list[dict] = []

    def generate_json(self, system: str, user: str, schema: dict) -> dict:
        from app.llm.base import LLMError

        self.calls.append({"system": system, "user": user})
        if self.fail or self.response is None:
            raise LLMError("fake failure")
        return self.response
