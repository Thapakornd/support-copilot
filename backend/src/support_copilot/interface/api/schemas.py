from typing import Annotated

from pydantic import BaseModel, ConfigDict, StringConstraints

from support_copilot.domain.entities import AnswerStatus


class ChatRequest(BaseModel):
    question: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]
    category: str | None = None


class ChatSource(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    number: int
    document_id: str
    revision_id: str
    chunk_set_id: str
    chunk_id: str
    title: str
    heading_path: list[str]
    source_url: str


class ChatResponse(BaseModel):
    answer: str
    status: AnswerStatus
    sources: list[ChatSource]
