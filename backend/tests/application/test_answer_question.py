import pytest

from support_copilot.application.use_cases.answer_question import AnswerQuestion


class FakeEncoder:
    def __init__(self):
        self.queries = []

    def token_count(self, text, *, query=False):
        assert query
        return len(text.split())

    def encode_queries(self, texts):
        self.queries.extend(texts)
        return [[1.0, 0.0]]


class FakeRetriever:
    def __init__(self, passages=()):
        self.passages = passages
        self.searches = []

    def resolve_category(self, category):
        return {"Connectivity": "connectivity", "connectivity": "connectivity"}.get(
            category
        )

    def retrieve(self, vector, category, limit):
        self.searches.append((vector, category, limit))
        return list(self.passages)


class FakeLLM:
    def __init__(self, result=None):
        self.result = result
        self.calls = []

    def answer(self, question, passages):
        self.calls.append((question, passages))
        return self.result


def build(*, encoder=None, retriever=None, llm=None, **kwargs):
    return AnswerQuestion(
        llm or FakeLLM(),
        encoder=encoder or FakeEncoder(),
        retriever=retriever or FakeRetriever(),
        max_query_tokens=3,
        **kwargs,
    )


def passage(chunk, text="Check the route.", distance=0.1, *, title="Networking"):
    from support_copilot.domain.entities import RetrievedPassage

    return RetrievedPassage(
        "network-doc",
        "revision-1",
        "set-1",
        chunk,
        title,
        ("VPC",),
        "https://example.com/vpc",
        text,
        distance,
    )


@pytest.mark.parametrize("category", ["connectivity", "Connectivity", None])
def test_retrieval_uses_trimmed_question_and_canonical_category(category):
    encoder = FakeEncoder()
    retriever = FakeRetriever()
    build(encoder=encoder, retriever=retriever)(" check routes ", category)

    assert encoder.queries == ["check routes"]
    assert retriever.searches == [
        ([1.0, 0.0], "connectivity" if category else None, 20)
    ]


@pytest.mark.parametrize(
    ("question", "category"),
    [("   ", None), ("one two three four", None), ("routes", "unknown")],
)
def test_invalid_question_or_category_skips_query_encoding(question, category):
    from support_copilot.application.errors import InvalidChatRequest

    encoder = FakeEncoder()
    with pytest.raises(InvalidChatRequest):
        build(encoder=encoder)(question, category)

    assert encoder.queries == []


def test_weak_evidence_returns_clarification_without_generation():
    llm = FakeLLM()
    retriever = FakeRetriever([passage("weak", distance=0.8)])
    result = build(llm=llm, retriever=retriever)("routes")

    assert result.status == "insufficient_evidence"
    assert result.text.endswith("?")
    assert result.sources == ()
    assert llm.calls == []


def test_generation_receives_only_distinct_passages_within_the_budget():
    from support_copilot.domain.entities import GenerationResult

    retriever = FakeRetriever(
        [
            passage("weak", "weak", 0.7),
            passage("first", "check"),
            passage("duplicate", " CHECK ", 0.2),
            passage("long", "long passage", 0.2),
            passage("last", "logs", 0.3),
        ]
    )
    llm = FakeLLM(
        GenerationResult(status="insufficient_evidence", clarification="Which route?")
    )
    result = build(llm=llm, retriever=retriever, evidence_char_limit=37)("routes")

    assert [(item.id, item.text) for item in llm.calls[0][1]] == [
        ("S1", "check"),
        ("S2", "logs"),
    ]
    assert result.text == "Which route?"


def test_answer_numbers_exact_passages_in_order_of_first_citation():
    from support_copilot.domain.entities import CitedStep, GenerationResult

    retriever = FakeRetriever([passage("first"), passage("second", "Check logs.", 0.2)])
    llm = FakeLLM(
        GenerationResult(
            status="answered",
            steps=(
                CitedStep("Check logs.", ("S2",)),
                CitedStep("Review routes.", ("S1", "S2", "S1")),
            ),
        )
    )
    result = build(llm=llm, retriever=retriever)("routes")

    assert result.status == "answered"
    assert result.text == "Check logs. [1]\n\nReview routes. [2] [1]"
    assert [(source.number, source.chunk_id) for source in result.sources] == [
        (1, "second"),
        (2, "first"),
    ]
    assert result.sources[0].title == "Networking"
    assert result.sources[0].source_url == "https://example.com/vpc"


@pytest.mark.parametrize("source_ids", [(), ("S1", "S99")])
def test_unsupported_step_discards_the_entire_answer(source_ids):
    from support_copilot.domain.entities import CitedStep, GenerationResult

    retriever = FakeRetriever([passage("first")])
    llm = FakeLLM(
        GenerationResult(
            status="answered",
            steps=(
                CitedStep("Check the route.", ("S1",)),
                CitedStep("Fabricated instructions.", source_ids),
            ),
        )
    )
    result = build(llm=llm, retriever=retriever)("routes")

    assert result.status == "insufficient_evidence"
    assert result.sources == ()
    assert "Fabricated" not in result.text


def test_retriever_failure_is_typed_without_database_details():
    from support_copilot.application.errors import RetrievalUnavailable

    class UnavailableRetriever(FakeRetriever):
        def retrieve(self, vector, category, limit):
            raise RuntimeError("secret database details")

    with pytest.raises(
        RetrievalUnavailable, match="Retrieval is temporarily unavailable"
    ):
        build(retriever=UnavailableRetriever())("routes")


def test_generation_failure_is_typed_without_provider_details():
    from support_copilot.application.errors import GenerationUnavailable

    class UnavailableLLM(FakeLLM):
        def answer(self, question, passages):
            raise TimeoutError("secret provider details")

    with pytest.raises(
        GenerationUnavailable, match="Answer generation is temporarily unavailable"
    ):
        build(retriever=FakeRetriever([passage("first")]), llm=UnavailableLLM())(
            "routes"
        )


def test_large_titles_count_toward_evidence_budget():
    from support_copilot.domain.entities import GenerationResult

    retriever = FakeRetriever(
        [
            passage("long-title", "one", title="Very long headline of a document"),
            passage("fits", "two", title="VPC"),
        ]
    )
    llm = FakeLLM(
        GenerationResult(status="insufficient_evidence", clarification="Which route?")
    )
    build(llm=llm, retriever=retriever, evidence_char_limit=10)("routes")

    assert [(item.id, item.title, item.text) for item in llm.calls[0][1]] == [
        ("S1", "VPC", "two"),
    ]


def test_generated_text_cannot_insert_its_own_citation_marker():
    from support_copilot.domain.entities import CitedStep, GenerationResult

    retriever = FakeRetriever([passage("first")])
    llm = FakeLLM(
        GenerationResult(
            status="answered", steps=(CitedStep("Check the route. [99]", ("S1",)),)
        )
    )
    result = build(llm=llm, retriever=retriever)("routes")

    assert result.status == "insufficient_evidence"
    assert "99" not in result.text
    assert result.sources == ()
