import re
from math import isfinite

from support_copilot.application.errors import (
    GenerationUnavailable,
    InvalidChatRequest,
    RetrievalUnavailable,
)
from support_copilot.application.ports import EncoderPort, LLMPort, RetrieverPort
from support_copilot.domain.entities import (
    Answer,
    AnswerSource,
    EvidencePassage,
    RetrievedPassage,
)

CLARIFY_QUESTION = (
    "Which product or feature is affected, and what error or behavior are you seeing?"
)
CITATION_MARKER = re.compile(
    r"\[\s*(?:S)?\d+(?:\s*[,–-]\s*(?:S)?\d+)*\s*\]", re.IGNORECASE
)


class AnswerQuestion:
    def __init__(
        self,
        llm: LLMPort,
        *,
        encoder: EncoderPort,
        retriever: RetrieverPort,
        max_query_tokens: int,
        candidate_limit: int = 20,
        max_distance: float = 0.5,
        max_passages: int = 6,
        evidence_char_limit: int = 12_000,
    ) -> None:
        self.llm = llm
        self.encoder = encoder
        self.retriever = retriever
        self.max_query_tokens = max_query_tokens
        self.candidate_limit = candidate_limit
        self.max_distance = max_distance
        self.max_passages = max_passages
        self.evidence_char_limit = evidence_char_limit

    def __call__(self, question: str, category: str | None = None) -> Answer:
        question = question.strip()
        if not question:
            raise InvalidChatRequest("Enter a question.")

        try:
            if self.encoder.token_count(question, query=True) > self.max_query_tokens:
                raise InvalidChatRequest("Shorten the question and try again.")
            if category is not None:
                category = self.retriever.resolve_category(category)
                if category is None:
                    raise InvalidChatRequest("Choose a valid product category.")
            (vector,) = self.encoder.encode_queries([question])
            candidates = self.retriever.retrieve(vector, category, self.candidate_limit)
        except InvalidChatRequest:
            raise
        except Exception as exc:
            raise RetrievalUnavailable("Retrieval is temporarily unavailable.") from exc

        passages = self._select_passages(candidates)
        if not passages:
            return Answer(CLARIFY_QUESTION, "insufficient_evidence")

        evidence = tuple(
            EvidencePassage(
                passage_id, passage.title, passage.heading_path, passage.text
            )
            for passage_id, passage in passages.items()
        )
        try:
            generated = self.llm.answer(question, evidence)
        except Exception as exc:
            raise GenerationUnavailable(
                "Answer generation is temporarily unavailable."
            ) from exc

        if generated.status == "insufficient_evidence":
            clarification = generated.clarification or CLARIFY_QUESTION
            if CITATION_MARKER.search(clarification):
                clarification = CLARIFY_QUESTION
            return Answer(clarification, "insufficient_evidence")

        sources: dict[str, AnswerSource] = {}
        steps = []
        for step in generated.steps:
            if (
                CITATION_MARKER.search(step.text)
                or not step.source_ids
                or any(source_id not in passages for source_id in step.source_ids)
            ):
                return Answer(CLARIFY_QUESTION, "insufficient_evidence")
            citations = []
            for source_id in dict.fromkeys(step.source_ids):
                if source_id not in sources:
                    passage = passages[source_id]
                    sources[source_id] = AnswerSource(
                        number=len(sources) + 1,
                        document_id=passage.document_id,
                        revision_id=passage.revision_id,
                        chunk_set_id=passage.chunk_set_id,
                        chunk_id=passage.chunk_id,
                        title=passage.title,
                        heading_path=passage.heading_path,
                        source_url=passage.source_url,
                    )
                citations.append(f"[{sources[source_id].number}]")
            steps.append(f"{step.text} {' '.join(citations)}")

        if not steps:
            return Answer(CLARIFY_QUESTION, "insufficient_evidence")
        return Answer("\n\n".join(steps), "answered", tuple(sources.values()))

    def _select_passages(
        self, candidates: list[RetrievedPassage]
    ) -> dict[str, RetrievedPassage]:
        remaining_chars = self.evidence_char_limit
        seen_text = set()
        selected = {}
        for candidate in candidates:
            if len(selected) == self.max_passages:
                break
            if (
                not isfinite(candidate.distance)
                or candidate.distance > self.max_distance
            ):
                continue
            normalized = " ".join(candidate.text.casefold().split())
            passage_chars = (
                len(candidate.text)
                + len(candidate.title)
                + sum(map(len, candidate.heading_path))
            )
            if (
                not normalized
                or normalized in seen_text
                or passage_chars > remaining_chars
            ):
                continue
            selected[f"S{len(selected) + 1}"] = candidate
            seen_text.add(normalized)
            remaining_chars -= passage_chars
        return selected
