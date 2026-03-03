import asyncio
import os
from collections.abc import AsyncIterator
from copy import deepcopy
from typing import Any, Protocol

from dotenv import load_dotenv
from frozenlist import FrozenList
from langchain_core.messages import (
    AIMessage,
    BaseMessage,
    HumanMessage,
    SystemMessage,
)
from langchain_google_genai import ChatGoogleGenerativeAI
from pydantic import ValidationError

from kube_sentinel.agent.errors import ChatConfigurationError

from .errors import ChatProviderError, ChatStreamError

load_dotenv()

SYSTEM_PROMPT = (
    "You are Kube-Sentinel, an expert AI SRE assistant specialized in "
    "Kubernetes cluster management, incident response, and remediation. "
    "You provide clear, actionable advice. When discussing commands or "
    "configurations, use proper formatting with code blocks. "
    "Be concise with a natural modern English tone throughout. "
)


class LLMClient(Protocol):
    """
    This protocol is the boundary dependency for the ChatService.
    It defines the expected interface for any LLM client implementation,
    allowing for flexibility and testability.
    """

    def astream(
        self,
        *args: Any,
        **kwargs: Any,
    ) -> AsyncIterator[Any]: ...


class ChatService:
    """Manages LLM interactions with conversation memory."""

    def __init__(self, llm_client: LLMClient | None = None) -> None:

        GOOGLE_VERTEX_API_KEY = os.getenv("GOOGLE_VERTEX_API_KEY")
        GOOGLE_CLOUD_PROJECT = os.getenv("GOOGLE_CLOUD_PROJECT")

        try:
            if llm_client is not None:
                self._llm = llm_client
            else:
                self._llm = ChatGoogleGenerativeAI(
                    model="gemini-3-flash-preview",
                    # ChatGoogleGenerativeAI accepts SecretStr,
                    # no need to get_secret_value()
                    api_key=GOOGLE_VERTEX_API_KEY
                    if GOOGLE_VERTEX_API_KEY
                    else ChatConfigurationError(
                        "GOOGLE_VERTEX_API_KEY is required for LLM client initialization."
                    ),
                    project=GOOGLE_CLOUD_PROJECT
                    if GOOGLE_CLOUD_PROJECT
                    else ChatConfigurationError(
                        "GOOGLE_CLOUD_PROJECT is required for LLM client initialization."
                    ),
                    temperature=0.3,
                    vertexai=True,
                )
        except Exception as error:
            raise ChatProviderError(
                "Failed to initialize LLM provider."
            ) from error

        self._history: list[BaseMessage] = [
            SystemMessage(content=SYSTEM_PROMPT)
        ]

    def _rollback_user_turn(self, message: HumanMessage) -> None:
        # We use 'is' check to ensure we remove the exact message instance
        # we just added
        if self._history and self._history[-1] is message:
            self._history.pop()

    def _extract_token_text(self, chunk_content: object) -> str:
        # If the chunk a single string, return it directly.
        if isinstance(chunk_content, str):
            return chunk_content
        elif isinstance(chunk_content, list):
            parts: list[str] = []
            for item in chunk_content:
                # If the chunk is a list, concatenate all string parts.
                if isinstance(item, str):
                    parts.append(item)
                # If an item is a dict, extract the 'text' field.
                elif isinstance(item, dict):
                    text = item.get("text")
                    if isinstance(text, str):
                        parts.append(text)
            return "".join(parts)
        else:
            return ""

    """
    TODO: _history grows without limit. For long-lived sessions, 
    accumulated messages will exceed the token budget, causing API errors 
    or silent truncation. Consider adding a sliding window, token-count cap, 
    or summarization strategy.
    """

    async def stream(self, user_input: str) -> AsyncIterator[str]:
        """Stream LLM response tokens for a given user message."""

        if not user_input.strip():
            raise ChatStreamError("User input cannot be empty")

        message = HumanMessage(content=user_input)
        self._history.append(message)
        full_response = ""

        try:
            async for chunk in self._llm.astream(self._history):
                token = self._extract_token_text(chunk.content)
                if token:
                    full_response += token
                    yield token

            self._history.append(AIMessage(content=full_response))

        except asyncio.CancelledError:
            self._rollback_user_turn(message)
            raise

        # TODO : Implement 'Structured Output' to the LLM and add the validation check
        except ValidationError as error:
            self._rollback_user_turn(message)
            raise ChatStreamError(
                f"Assistant response failed schema validation: {error}"
            ) from error

        except Exception as error:
            self._rollback_user_turn(message)
            raise ChatProviderError(
                f"LLM Streaming failed: {error}"
            ) from error

    async def get_chat_history(self) -> FrozenList[BaseMessage]:
        """Get the chat history."""
        frozen_history = FrozenList(deepcopy(self._history))
        frozen_history.freeze()
        return frozen_history

    async def clear_chat_history(self) -> None:
        """Clear the chat history."""
        self._history = [SystemMessage(content=SYSTEM_PROMPT)]
        return None
