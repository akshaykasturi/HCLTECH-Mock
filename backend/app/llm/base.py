"""One interface for every LLM provider. The pipeline only ever talks to this."""
from typing import Protocol


class LLMClient(Protocol):
    name: str

    def generate_json(self, system: str, user: str, schema: dict) -> dict:
        """Return a dict matching `schema`. Raise LLMError on failure."""
        ...


class LLMError(Exception):
    """`errors` lists each provider's failure when a chain gives up. It lives on the exception,
    which belongs to one call, never on the shared client."""

    def __init__(self, message: str = "", errors: list[str] | None = None) -> None:
        super().__init__(message)
        self.errors = list(errors) if errors else [message]
