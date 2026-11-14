from dataclasses import dataclass


@dataclass(frozen=True)
class Answer:
    text: str
