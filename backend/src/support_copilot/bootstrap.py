"""Composition root: the only place that knows concrete classes."""

from support_copilot.application.use_cases.answer_question import AnswerQuestion
from support_copilot.core.config import settings
from support_copilot.infrastructure.langchain.llm import LangChainLLM


def build_answer_question() -> AnswerQuestion:
    return AnswerQuestion(
        LangChainLLM(
            settings.llm_model,
            provider=settings.llm_provider,
            api_key=settings.anthropic_api_key.get_secret_value(),
        )
    )


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


def build_embedding_worker():
    from support_copilot.core.config import WorkerSettings
    from support_copilot.infrastructure.embeddings.chunker import TokenAwareChunker
    from support_copilot.infrastructure.embeddings.sentence_transformer import (
        SentenceTransformerEncoder,
    )
    from support_copilot.infrastructure.postgres.knowledge_repository import (
        KnowledgeRepository,
    )

    runtime = WorkerSettings()
    config = runtime.effective_config()
    store = KnowledgeRepository(
        runtime.database_url.get_secret_value(),
        lease_seconds=runtime.lease_seconds,
        max_attempts=runtime.max_attempts,
    )

    def encoder_factory():
        return SentenceTransformerEncoder(
            config,
            device=runtime.device,
            batch_size=runtime.batch_size,
            offline=runtime.offline,
        )

    return store, encoder_factory, TokenAwareChunker(), runtime
