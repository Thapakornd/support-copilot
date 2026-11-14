from support_copilot.application.use_cases.answer_question import AnswerQuestion


class FakeLLM:
    def answer(self, question: str) -> str:
        return f"echo: {question}"


def test_answer_question():
    assert AnswerQuestion(FakeLLM())("hi").text == "echo: hi"


def test_answer_question_scopes_by_category():
    assert AnswerQuestion(FakeLLM())("hi", "Connectivity").text == "echo: Product area: Connectivity\n\nhi"
