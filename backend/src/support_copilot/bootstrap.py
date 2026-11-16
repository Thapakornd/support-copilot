"""Composition root: the only place that knows concrete classes."""

from support_copilot.application.use_cases.answer_question import AnswerQuestion
from support_copilot.core.config import settings
from support_copilot.infrastructure.langchain.llm import LangChainLLM


def build_answer_question() -> AnswerQuestion:
    return AnswerQuestion(LangChainLLM(settings.llm_model))


def build_embedding_admission():
    from support_copilot.core.config import WorkerSettings
    from support_copilot.infrastructure.postgres.knowledge_repository import (
        KnowledgeRepository,
    )

    config = WorkerSettings()
    store = KnowledgeRepository(
        config.database_url.get_secret_value(),
        lease_seconds=config.lease_seconds,
        max_attempts=config.max_attempts,
    )
    return store, config.effective_config()
