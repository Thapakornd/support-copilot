from threading import Lock

from fastapi import APIRouter, HTTPException

from support_copilot.application.errors import (
    GenerationUnavailable,
    InvalidChatRequest,
    RetrievalUnavailable,
)
from support_copilot.application.use_cases.answer_question import AnswerQuestion
from support_copilot.bootstrap import build_answer_question
from support_copilot.interface.api.schemas import ChatRequest, ChatResponse, ChatSource

router = APIRouter()


class _AnswerQuestionCache:
    def __init__(self) -> None:
        self._lock = Lock()
        self._answer_question: AnswerQuestion | None = None

    def __call__(self) -> AnswerQuestion:
        answer_question = self._answer_question
        if answer_question is not None:
            return answer_question

        with self._lock:
            if self._answer_question is None:
                self._answer_question = build_answer_question()
            return self._answer_question

    def cache_clear(self) -> None:
        with self._lock:
            self._answer_question = None


get_answer_question = _AnswerQuestionCache()


@router.post("/chat")
def chat(req: ChatRequest) -> ChatResponse:
    try:
        result = get_answer_question()(req.question, req.category)
    except InvalidChatRequest as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except RetrievalUnavailable as exc:
        raise HTTPException(
            status_code=503, detail="Retrieval is temporarily unavailable."
        ) from exc
    except GenerationUnavailable as exc:
        raise HTTPException(
            status_code=502, detail="Answer generation is temporarily unavailable."
        ) from exc

    return ChatResponse(
        answer=result.text,
        status=result.status,
        sources=[ChatSource.model_validate(source) for source in result.sources],
    )
