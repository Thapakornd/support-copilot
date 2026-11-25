from dataclasses import dataclass
from typing import Literal
from uuid import UUID

AnswerStatus = Literal["answered", "insufficient_evidence"]


@dataclass(frozen=True)
class RetrievedPassage:
    document_id: str
    revision_id: str
    chunk_set_id: str
    chunk_id: str
    title: str
    heading_path: tuple[str, ...]
    source_url: str
    text: str
    distance: float


@dataclass(frozen=True)
class EvidencePassage:
    id: str
    title: str
    heading_path: tuple[str, ...]
    text: str


@dataclass(frozen=True)
class CitedStep:
    text: str
    source_ids: tuple[str, ...]


@dataclass(frozen=True)
class GenerationResult:
    status: AnswerStatus
    steps: tuple[CitedStep, ...] = ()
    clarification: str | None = None


@dataclass(frozen=True)
class AnswerSource:
    number: int
    document_id: str
    revision_id: str
    chunk_set_id: str
    chunk_id: str
    title: str
    heading_path: tuple[str, ...]
    source_url: str


@dataclass(frozen=True)
class Answer:
    text: str
    status: AnswerStatus
    sources: tuple[AnswerSource, ...] = ()


@dataclass(frozen=True)
class CurrentUser:
    id: UUID
    name: str
    email: str
    company: str
    role: Literal["customer", "agent"]
    account_id: UUID | None
