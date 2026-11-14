"""Composition root: the only place that knows concrete classes."""
from support_copilot.application.use_cases.answer_question import AnswerQuestion
from support_copilot.core.config import settings
from support_copilot.infrastructure.langchain.llm import LangChainLLM


def build_answer_question() -> AnswerQuestion:
    return AnswerQuestion(LangChainLLM(settings.llm_model))
