from langchain.chat_models import init_chat_model


class LangChainLLM:
    """Adapter implementing LLMPort."""

    def __init__(self, model: str) -> None:
        self.model = init_chat_model(model)

    def answer(self, question: str) -> str:
        return self.model.invoke(question).text
