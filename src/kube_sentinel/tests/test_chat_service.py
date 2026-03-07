import asyncio
from collections.abc import AsyncGenerator
from types import SimpleNamespace
from typing import Any

import pytest
from frozenlist import FrozenList
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, \
    BaseMessage

from kube_sentinel.agent.chat_service import ChatService
from kube_sentinel.agent.errors import ChatStreamError, ChatProviderError


class ScriptedLLM:
    def __init__(
            self,
            chunks: list[str] | None = None,
            exc: BaseException | None = None,
    ) -> None:
        self.chunks = chunks or []
        self._exc = exc

    async def astream(self, *args: Any, **kwargs: Any) -> AsyncGenerator[
        Any, None]:
        for chunk in self.chunks:
            yield SimpleNamespace(content=chunk)
        if self._exc is not None:
            raise self._exc


@pytest.mark.asyncio
async def test_history_initialization() -> None:
    """Test that the chat history initializes with the
    correct system prompt and structure."""
    # Initialize service, inspect baseline invariant
    service: ChatService = ChatService()
    history: FrozenList[BaseMessage] = await service.get_chat_history()
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
    chunks: list[str] = ["Hello", " ", "!"]
    scripted_llm: ScriptedLLM = ScriptedLLM(chunks=chunks)

    service: ChatService = ChatService(llm_client=scripted_llm)

    collected_tokens: list[str] = []

    user_input: str = "What is Kubernetes?"

    async for token in service.stream(user_input):
        assert isinstance(token, str), "Streamed token must be a string"
        collected_tokens.append(token)

    # This ensures the stream() method correctly extracts and yields content
    assert collected_tokens == chunks, (
        f"Collected tokens {collected_tokens} do not match expected chunks {chunks}"
    )

    # This validates that streaming works end-to-end
    # from chunk to final content
    expected_full_response: str = "".join(chunks)
    actual_full_response: str = "".join(collected_tokens)
    assert actual_full_response == expected_full_response, (
        f"Full response '{actual_full_response}' does not match expected '{expected_full_response}'"
    )

    history: FrozenList[BaseMessage] = await service.get_chat_history()

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

    first_ai_response: str = "Response 1"

    scripted_llm: ScriptedLLM = ScriptedLLM([first_ai_response])

    service: ChatService = ChatService(llm_client=scripted_llm)

    history_before_first_input: FrozenList[
        BaseMessage] = await service.get_chat_history()
    assert len(history_before_first_input) == 1, (
        "History should start with only the system message"
    )

    user_input_1: str = "First question?"

    async for _ in service.stream(user_input_1):
        pass

    # VERIFY: History after first stream
    # Should have: [SystemMessage, HumanMessage(input), AIMessage(response)]
    history_after_first_input: FrozenList[
        BaseMessage] = await service.get_chat_history()

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

    second_ai_response: str = "Response 2"

    scripted_llm.chunks = [second_ai_response]
    user_input_2: str = "Second question?"

    async for _ in service.stream(user_input_2):
        pass

    # VERIFY: History after second stream
    # Should have: [SystemMessage, HumanMessage(1), AIMessage(1), HumanMessage(2), AIMessage(2)]

    history_after_second_input: FrozenList[
        BaseMessage] = await service.get_chat_history()

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


@pytest.mark.asyncio
async def test_clear_chat_history() -> None:
    """
    Test that ChatService correctly clears chat history and resets
    to just the system message.

    This test validates:
    1. History contains messages before clearing
    2. After clear_chat_history(), history is reset to only system message
    3. Clearing multiple times maintains the invariant
    """
    scripted_llm: ScriptedLLM = ScriptedLLM(chunks=["Response 1"])
    service: ChatService = ChatService(llm_client=scripted_llm)

    async for _ in service.stream("First question?"):
        pass
    history_before_cleanup: FrozenList[
        BaseMessage] = await service.get_chat_history()

    assert isinstance(history_before_cleanup[0],
                      SystemMessage), "The first message should be a SystemMessage"

    assert len(
            history_before_cleanup) == 3, "History should have three messages before cleanup"

    await service.clear_chat_history()
    history_after_first_cleanup: FrozenList[
        BaseMessage] = await service.get_chat_history()
    assert len(
            history_after_first_cleanup
    ) == 1, "History should have one system message after cleanup"
    assert isinstance(history_after_first_cleanup[0], SystemMessage), (
        "After cleanup, first message should be a SystemMessage"
    )

    await service.clear_chat_history()
    history_after_second_cleanup: FrozenList[
        BaseMessage] = await service.get_chat_history()
    assert len(
            history_after_second_cleanup
    ) == 1, "History should have one system message after second cleanup"
    assert isinstance(history_after_second_cleanup[0],
                      SystemMessage), "After second cleanup, first message should be a SystemMessage"


@pytest.mark.asyncio
async def test_stream_empty_input() -> None:
    """
    Test that ChatService raises ChatStreamError when given empty or
    whitespace-only user input.

    This test validates:
    1. Empty string raises ChatStreamError
    2. Whitespace-only string raises ChatStreamError
    3. Error message is descriptive
    4. No messages are added to history on error
    """
    service: ChatService = ChatService(llm_client=ScriptedLLM())
    with pytest.raises(ChatStreamError) as exception_info:
        async for _ in service.stream(""):
            pass
    assert str(exception_info.value) == "User input cannot be empty"

    with pytest.raises(ChatStreamError) as exception_info:
        async for _ in service.stream("   "):
            pass

    assert str(exception_info.value) == "User input cannot be empty"

    history: FrozenList[BaseMessage] = await service.get_chat_history()
    assert len(
            history) == 1, "History should start with only the system message"
    assert isinstance(history[0],
                      SystemMessage), "First message should be a SystemMessage"

    return None


@pytest.mark.asyncio
async def test_stream_with_llm_error() -> None:
    """
    Test that ChatService raises ChatProviderError when the LLM raises
    a generic exception during streaming, and rolls back history.

    This test validates:
    1. ChatProviderError is raised on LLM provider failure
    2. The original error is wrapped (chained) inside ChatProviderError
    3. History is rolled back — user message is not persisted on
    failure
    """
    scripted_llm: ScriptedLLM = ScriptedLLM(exc=Exception("LLM provider error"))
    service: ChatService = ChatService(llm_client=scripted_llm)
    with pytest.raises(ChatProviderError) as exception_info:
        async for _ in service.stream("What is a Pod?"):
            pass

    # Verify the original cause is chained onto the raised error
    assert exception_info.value.__cause__ is not None
    assert "LLM provider error" in str(exception_info.value.__cause__)

    # Verify history was rolled back - only system message should remain
    history: FrozenList[BaseMessage] = await service.get_chat_history()
    assert len(
            history) == 1, "History should be rolled back after the error to just the system message"
    assert isinstance(history[0],
                      SystemMessage), "First message should be a SystemMessage"


@pytest.mark.asyncio
async def test_stream_with_cancelled_error() -> None:
    """
    Test that ChatService re-raises CancelledError and
    rolls back history when a stream is canceled.

    This test validates:
    1. asyncio.CancelledError propagates without being wrapped
    2. History is rolled back — a user message is not
    persisted on cancellation
    """
    scripted_llm: ScriptedLLM = ScriptedLLM(exc=asyncio.CancelledError())
    service: ChatService = ChatService(llm_client=scripted_llm)

    with pytest.raises(asyncio.CancelledError):
        async for _ in service.stream("What is a namespace?"):
            pass

    history: FrozenList[BaseMessage] = await service.get_chat_history()

    assert len(history) == 1, ("History should be rolled back after " +
                               "'asyncio.CancelledError'")
    assert isinstance(history[0], SystemMessage), (
        "The first message should be a SystemMessage"
    )
    return None
