"""Composition root: the only place that knows concrete classes."""

from support_copilot.application.errors import (
    GenerationUnavailable,
    RetrievalUnavailable,
    ServiceUnavailable,
)
from support_copilot.application.use_cases.answer_question import AnswerQuestion
from support_copilot.core.config import EmbeddingSettings, settings
from support_copilot.infrastructure.langchain.llm import LangChainLLM


def build_answer_question() -> AnswerQuestion:
    from support_copilot.infrastructure.embeddings.sentence_transformer import (
        SentenceTransformerEncoder,
    )
    from support_copilot.infrastructure.postgres.retrieval import PostgresRetriever

    try:
        database_url = settings.database_url.get_secret_value()
        if not database_url.strip():
            raise ValueError("DATABASE_URL is required for chat")
        runtime = EmbeddingSettings()
        config = runtime.effective_config()
        retriever = PostgresRetriever(database_url, config)
        retriever.validate_configuration()
        encoder = SentenceTransformerEncoder(
            config,
            device=runtime.device,
            batch_size=runtime.batch_size,
            offline=runtime.offline,
        )
        # Load and validate the shared model before request threads can use it.
        encoder.token_count("", query=True)
    except Exception as exc:
        raise RetrievalUnavailable("Retrieval is temporarily unavailable.") from exc

    try:
        api_key = (
            settings.openrouter_api_key
            if settings.llm_provider == "openrouter"
            else settings.anthropic_api_key
        )
        llm = LangChainLLM(
            settings.llm_model,
            provider=settings.llm_provider,
            api_key=api_key.get_secret_value(),
            timeout=settings.llm_timeout_seconds,
        )
    except Exception as exc:
        raise GenerationUnavailable(
            "Answer generation is temporarily unavailable."
        ) from exc

    return AnswerQuestion(
        llm,
        encoder=encoder,
        retriever=retriever,
        max_query_tokens=config.tokenizer_limit,
        candidate_limit=settings.chat_candidate_limit,
        max_distance=settings.chat_max_distance,
        max_passages=settings.chat_max_passages,
        evidence_char_limit=settings.chat_evidence_char_limit,
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


def build_database():
    from support_copilot.infrastructure.postgres.connection import Database

    dsn = settings.database_url.get_secret_value().strip()
    if not dsn:
        raise ServiceUnavailable("DATABASE_URL is not configured.")
    return Database(dsn)


def build_accounts():
    from support_copilot.infrastructure.postgres.accounts import AccountRepository

    return AccountRepository(build_database())


def build_articles():
    from support_copilot.infrastructure.postgres.articles import ArticleRepository

    return ArticleRepository(build_database())


def build_tickets():
    from support_copilot.infrastructure.postgres.tickets import TicketRepository

    return TicketRepository(build_database())
