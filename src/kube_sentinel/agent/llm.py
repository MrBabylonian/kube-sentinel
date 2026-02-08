from collections.abc import AsyncIterator

from langchain_core.messages import (
    AIMessage,
    BaseMessage,
    HumanMessage,
    SystemMessage,
)
from langchain_google_genai import ChatGoogleGenerativeAI
from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")
    GOOGLE_VERTEX_API_KEY: SecretStr
    GOOGLE_CLOUD_PROJECT: SecretStr


SYSTEM_PROMPT = (
    "You are Kube-Sentinel, an expert AI SRE assistant specialized in "
    "Kubernetes cluster management, incident response, and remediation. "
    "You provide clear, actionable advice. When discussing commands or "
    "configurations, use proper formatting with code blocks. "
    "Be concise with a natural modern English tone throughout. "
)


class ChatService:
    """Manages LLM interactions with conversation memory."""

    def __init__(self) -> None:
        self._settings = Settings()  # type: ignore[call-arg]
        self._llm = ChatGoogleGenerativeAI(
            model="gemini-3-flash-preview",
            # ChatGoogleGenerativeAI accepts SecretStr,
            # no need to get_secret_value()
            api_key=self._settings.GOOGLE_VERTEX_API_KEY,
            google_cloud_project=self._settings.GOOGLE_CLOUD_PROJECT,
            temperature=0.3,
            vertexai=True,
        )
        self._history: list[BaseMessage] = [
            SystemMessage(content=SYSTEM_PROMPT)
        ]
        return None

    """
    TODO: _history grows without limit. For long-lived sessions, accumulated messages will exceed the token budget, causing API errors or silent truncation. Consider adding a sliding window, token-count cap, or summarization strategy.
    """

    async def stream(self, user_input: str) -> AsyncIterator[str]:
        """Stream LLM response tokens for a given user message."""
        message = HumanMessage(content=user_input)
        self._history.append(message)
        full_response = ""
        try:
            async for chunk in self._llm.astream(self._history):
                token = chunk.content
                if isinstance(token, str):
                    full_response += token
                    yield token
            self._history.append(AIMessage(content=full_response))
        except Exception:
            # list.remove() deletes the first element equal to message.
            # If the user sends the same text twice,
            # it will remove the earlier message
            # instead of the one just appended.
            # Since the message was appended at the end,
            # self._history.pop() is both correct and O(1).
            self._history.pop(self._history.index(message))
            raise

    async def clear_chat_history(self) -> None:
        """Clear the chat history."""
        self._history = [SystemMessage(content=SYSTEM_PROMPT)]
        return None
