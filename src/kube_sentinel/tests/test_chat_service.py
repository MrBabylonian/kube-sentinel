from collections.abc import AsyncGenerator
from types import SimpleNamespace
from typing import Any

import pytest
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage

from kube_sentinel.agent.chat_service import ChatService


class ScriptedLLM:
    def __init__(
        self,
        chunks: list[str] | None = None,
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


@pytest.mark.asyncio
async def test_stream_appends_to_history() -> None:
    """
    Test that ChatService correctly appends HumanMessage and
    AIMessage to history.

    This test validates:
    1. User input is appended as a HumanMessage before streaming
    2. LLM response is appended as an AIMessage after streaming completes
    3. Messages are appended in the correct order
    4. Multiple calls accumulate messages correctly
    """

    first_ai_response = "Response 1"

    scripted_llm = ScriptedLLM([first_ai_response])

    service = ChatService(llm_client=scripted_llm)

    history_before_first_input = await service.get_chat_history()
    assert len(history_before_first_input) == 1, (
        "History should start with only the system message"
    )

    user_input_1 = "First question?"

    async for _ in service.stream(user_input_1):
        pass

    # VERIFY: History after first stream
    # Should have: [SystemMessage, HumanMessage(input), AIMessage(response)]
    history_after_first_input = await service.get_chat_history()

    assert len(history_after_first_input) == 3, (
        "After first input, history should have 3 messages"
        "(system, human, ai response)"
    )

    assert history_after_first_input[1].content == user_input_1, (
        f"After first input, second message should be the user's HumanMessage with content '{user_input_1}'"
    )
    assert history_after_first_input[2].content == first_ai_response, (
        f"After first input, third message should be the AI's response with content '{first_ai_response}'"
    )

    second_ai_response = "Response 2"

    scripted_llm.chunks = [second_ai_response]
    user_input_2 = "Second question?"

    async for _ in service.stream(user_input_2):
        pass

    # VERIFY: History after second stream
    # Should have: [SystemMessage, HumanMessage(1), AIMessage(1), HumanMessage(2), AIMessage(2)]

    history_after_second_input = await service.get_chat_history()

    assert len(history_after_second_input) == 5, (
        "After second input, history should have 5 messages"
        "(system, human1, ai response 1, human2, ai response 2)"
    )

    assert isinstance(history_after_second_input[0], SystemMessage), (
        "First message should be a SystemMessage"
    )
    assert (
        isinstance(history_after_second_input[1], HumanMessage)
        and history_after_second_input[1].content == user_input_1
    ), (
        "Second message should be the first HumanMessage with content matching user_input_1"
    )
    assert (
        isinstance(history_after_second_input[2], AIMessage)
        and history_after_second_input[2].content == first_ai_response
    ), (
        "Third message should be the first AIMessage with content matching first_ai_response"
    )
    assert (
        isinstance(history_after_second_input[3], HumanMessage)
        and history_after_second_input[3].content == user_input_2
    ), (
        "Fourth message should be the second HumanMessage with content matching user_input_2"
    )
    assert (
        isinstance(history_after_second_input[4], AIMessage)
    ) and history_after_second_input[4].content == second_ai_response, (
        "Fifth message should be the second AIMessage with content matching second_ai_response"
    )
