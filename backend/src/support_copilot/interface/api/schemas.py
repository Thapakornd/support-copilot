from pydantic import BaseModel


class ChatRequest(BaseModel):
    question: str
    category: str | None = None  # narrows the search scope, e.g. "Connectivity"


class ChatResponse(BaseModel):
    answer: str
