import os
from collections.abc import AsyncIterator

from dotenv import load_dotenv
from langchain_core.messages import (
    AIMessage,
    BaseMessage,
    HumanMessage,
    SystemMessage,
)
from langchain_google_genai import ChatGoogleGenerativeAI

load_dotenv(verbose=True)

GOOGLE_VERTEX_API_KEY = os.getenv("GOOGLE_VERTEX_API_KEY")
GOOGLE_CLOUD_PROJECT = os.getenv("GOOGLE_CLOUD_PROJECT")

if not GOOGLE_VERTEX_API_KEY or not GOOGLE_CLOUD_PROJECT:
    raise ValueError(
        "GOOGLE_VERTEX_API_KEY and GOOGLE_CLOUD_PROJECT must be set"
    )

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
        self._llm = ChatGoogleGenerativeAI(
            model="gemini-3-flash-preview",
            api_key=GOOGLE_VERTEX_API_KEY,
            google_cloud_project=GOOGLE_CLOUD_PROJECT,
            temperature=0.3,
            vertexai=True,
        )
        self._history: list[BaseMessage] = [
            SystemMessage(content=SYSTEM_PROMPT)
        ]
        return None

    async def stream(self, user_input: str) -> AsyncIterator[str]:
        """Stream LLM response tokens for a given user message."""
        self._history.append(HumanMessage(content=user_input))
        full_response = ""
        async for chunk in self._llm.astream(self._history):
            token = chunk.content
            if isinstance(token, str):
                full_response += token
                yield token
        self._history.append(AIMessage(content=full_response))

    async def clear_chat_history(self) -> None:
        """Clear the chat history."""
        self._history = [SystemMessage(content=SYSTEM_PROMPT)]
        return None
