import pytest
from fastapi.testclient import TestClient

from support_copilot.application.errors import (
    GenerationUnavailable,
    InvalidChatRequest,
    RetrievalUnavailable,
)
from support_copilot.domain.entities import Answer, AnswerSource
from support_copilot.interface.api.main import app
from support_copilot.interface.api.routes import chat


@pytest.fixture
def client():
    chat.get_answer_question.cache_clear()
    yield TestClient(app)
    chat.get_answer_question.cache_clear()


def test_chat_serializes_citations_from_the_use_case(monkeypatch, client):
    def answer(question, category):
        assert question == "Which routes?"
        assert category == "Connectivity"
        return Answer(
            "Check the route. [1]",
            "answered",
            (
                AnswerSource(
                    1,
                    "doc",
                    "rev",
                    "set",
                    "chunk",
                    "VPC routing",
                    ("Route tables",),
                    "https://example.com/routes",
                ),
            ),
        )

    monkeypatch.setattr(chat, "build_answer_question", lambda: answer)
    response = client.post(
        "/chat", json={"question": "  Which routes? ", "category": "Connectivity"}
    )

    assert response.status_code == 200
    assert response.json() == {
        "answer": "Check the route. [1]",
        "status": "answered",
        "sources": [
            {
                "number": 1,
                "document_id": "doc",
                "revision_id": "rev",
                "chunk_set_id": "set",
                "chunk_id": "chunk",
                "title": "VPC routing",
                "heading_path": ["Route tables"],
                "source_url": "https://example.com/routes",
            }
        ],
    }


def test_abstention_is_a_successful_response_without_sources(monkeypatch, client):
    def answer(question, category):
        return Answer("Which route is affected?", "insufficient_evidence")

    monkeypatch.setattr(chat, "build_answer_question", lambda: answer)
    response = client.post("/chat", json={"question": "Routes?", "category": None})

    assert response.status_code == 200
    assert response.json() == {
        "answer": "Which route is affected?",
        "status": "insufficient_evidence",
        "sources": [],
    }


def test_blank_question_is_rejected_before_initializing_chat(monkeypatch, client):
    def build():
        pytest.fail("Blank questions should never initialize the chat dependencies")

    monkeypatch.setattr(chat, "build_answer_question", build)

    assert client.post("/chat", json={"question": "   "}).status_code == 422


def test_invalid_category_becomes_422(monkeypatch, client):
    def answer(question, category):
        raise InvalidChatRequest("Choose a valid product category.")

    monkeypatch.setattr(chat, "build_answer_question", lambda: answer)
    response = client.post("/chat", json={"question": "Routes?", "category": "unknown"})

    assert response.status_code == 422
    assert response.json()["detail"] == "Choose a valid product category."


@pytest.mark.parametrize(
    ("error", "status"),
    [(RetrievalUnavailable, 503), (GenerationUnavailable, 502)],
)
@pytest.mark.parametrize("during_build", [True, False])
def test_chat_hides_failure_details_and_allows_retry(
    monkeypatch, client, error, status, during_build
):
    def fail(*args):
        raise error("internal service detail")

    monkeypatch.setattr(
        chat, "build_answer_question", fail if during_build else lambda: fail
    )
    response = client.post("/chat", json={"question": "Routes?"})

    assert response.status_code == status
    assert "internal service detail" not in response.text
    assert response.json()["detail"]

    if during_build:
        monkeypatch.setattr(
            chat,
            "build_answer_question",
            lambda: lambda *_: Answer("Which route?", "insufficient_evidence"),
        )
        assert client.post("/chat", json={"question": "Routes?"}).status_code == 200


def test_chat_construction_is_shared_by_concurrent_callers(monkeypatch, client):
    from concurrent.futures import ThreadPoolExecutor
    from threading import Event, Lock

    first_started = Event()
    second_started = Event()
    duplicate_build = Event()
    release_build = Event()
    calls = 0
    calls_lock = Lock()
    instance = object()

    def build():
        nonlocal calls
        with calls_lock:
            calls += 1
            if calls > 1:
                duplicate_build.set()
        first_started.set()
        assert release_build.wait(5)
        return instance

    def get_second():
        second_started.set()
        return chat.get_answer_question()

    monkeypatch.setattr(chat, "build_answer_question", build)
    with ThreadPoolExecutor(max_workers=2) as pool:
        first = pool.submit(chat.get_answer_question)
        assert first_started.wait(5)
        second = pool.submit(get_second)
        try:
            assert second_started.wait(5)
            assert not duplicate_build.wait(0.2)
        finally:
            release_build.set()
        assert first.result() is instance
        assert second.result() is instance

    assert calls == 1


def test_unavailable_chat_during_startup_preserves_health_and_can_recover(
    monkeypatch, client
):
    builds = 0

    def build():
        nonlocal builds
        builds += 1
        if builds == 1:
            raise RetrievalUnavailable("private database status")
        return lambda *_: Answer("Which route?", "insufficient_evidence")

    monkeypatch.setattr(chat, "build_answer_question", build)
    with client:
        assert builds == 1
        assert client.get("/health").status_code == 200
        assert client.post("/chat", json={"question": "Routes?"}).status_code == 200
    assert builds == 2
