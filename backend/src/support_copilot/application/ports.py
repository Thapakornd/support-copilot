from typing import Protocol


class LLMPort(Protocol):
    def answer(self, question: str) -> str: ...
