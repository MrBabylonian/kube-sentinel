from collections.abc import AsyncGenerator
from types import SimpleNamespace
from typing import Any

import pytest
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage

from kube_sentinel.agent.chat_service import ChatService


class ScriptedLLM:
    def __init__(
        self,
        chunks: list[str] | list[list[Any]] | None = None,
        exc: Exception | None = None,
    ) -> None:
        self.chunks = chunks or []
        self._exc = exc

    async def astream(self, *args: Any, **kwargs: Any) -> AsyncGenerator[Any]:
        for chunk in self.chunks:
            yield SimpleNamespace(content=chunk)
        if self._exc is not None:
            raise self._exc


@pytest.mark.asyncio
async def test_history_initialization() -> None:
    """Test that the chat history initializes with the
    correct system prompt and structure."""
    # Initialize service, inspect baseline invariant
    service = ChatService()
    history = await service.get_chat_history()
    assert len(history) == 1, "History should start with one system message"

    assert isinstance(history[0], SystemMessage), (
        "First message in the history must be type SystemMessage"
    )
    return None


@pytest.mark.asyncio
async def test_stream_success() -> None:
    """
    Test that ChatService successfully streams LLM responses
    with multiple token chunks.

    This test validates:
    1. Multiple chunks are correctly yielded as seperate tokens
    2. Tokens are accumulated into a complete response string
    3. The full response is added to chat history as an AIMessage
    4. The original user message is preserved in history
    """

    # This simulates a realistic streaming behavior where the LLM provider
    # sends response content in small pieces (e.g., "Hello", " ", "world", "!")
    chunks = ["Hello", " ", "!"]
    scripted_llm = ScriptedLLM(chunks=chunks)

    service = ChatService(llm_client=scripted_llm)

    collected_tokens: list[str] = []

    user_input = "What is Kubernetes?"

    async for token in service.stream(user_input):
        assert isinstance(token, str), "Streamed token must be a string"
        collected_tokens.append(token)

    # This ensures the stream() method correctly extracts and yields content
    assert collected_tokens == chunks, (
        f"Collected tokens {collected_tokens} do not match expected chunks {chunks}"
    )

    # This validates that streaming works end-to-end
    # from chunk to final content
    expected_full_response = "".join(chunks)
    actual_full_response = "".join(collected_tokens)
    assert actual_full_response == expected_full_response, (
        f"Full response '{actual_full_response}' does not match expected '{expected_full_response}'"
    )

    history = await service.get_chat_history()

    assert len(history) == 3, (
        f"History should contain 3 messages (user input, system prompt,"
        f"and AI response), but got {len(history)}"
    )

    assert isinstance(history[0], SystemMessage), (
        "First message should be a SystemMessage"
    )
    assert isinstance(history[1], HumanMessage), (
        "Second message should be the user's HumanMessage"
    )
    assert isinstance(history[2], AIMessage), (
        "Third message should be the AI's response as an AIMessage"
    )

    assert history[1].content == user_input, (
        f"Human message content '{history[1].content}'"
        f"does not match user input '{user_input}'"
    )

    assert history[2].content == expected_full_response, (
        f"AI message content '{history[2].content}' does not match expected full response '{expected_full_response}'"
    )

    return None
