from support_copilot.application.ports import LLMPort
from support_copilot.domain.entities import Answer


class AnswerQuestion:
    def __init__(self, llm: LLMPort) -> None:
        self.llm = llm

    def __call__(self, question: str, category: str | None = None) -> Answer:
        # ponytail: category only scopes the prompt today; filter retriever metadata on it once RAG lands
        prompt = f"Product area: {category}\n\n{question}" if category else question
        return Answer(text=self.llm.answer(prompt))
