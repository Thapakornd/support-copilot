from functools import lru_cache
from typing import Annotated

from fastapi import APIRouter, Depends

from support_copilot.application.use_cases.answer_question import AnswerQuestion
from support_copilot.bootstrap import build_answer_question
from support_copilot.interface.api.schemas import ChatRequest, ChatResponse

router = APIRouter()


@lru_cache
def get_answer_question() -> AnswerQuestion:
    return build_answer_question()


@router.post("/chat")
def chat(req: ChatRequest, uc: Annotated[AnswerQuestion, Depends(get_answer_question)]) -> ChatResponse:
    return ChatResponse(answer=uc(req.question, req.category).text)
