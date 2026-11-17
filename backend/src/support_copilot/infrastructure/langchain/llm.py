from langchain.chat_models import init_chat_model


class LangChainLLM:
    """Adapter implementing LLMPort."""

    def __init__(self, model: str, *, provider: str, api_key: str) -> None:
        if not model.strip():
            raise ValueError("Set LLM_MODEL before using chat")
        self.model = init_chat_model(model, model_provider=provider, api_key=api_key)

    def answer(self, question: str) -> str:
        return self.model.invoke(question).text
