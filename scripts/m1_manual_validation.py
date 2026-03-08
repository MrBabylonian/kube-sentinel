"""
M1 Manual Validation Script
============================
Non-interactive terminal validation for M1 DoD manual checks:
  1. Multi-turn context retention
  2. Reset/clear behavior
  3. Error recovery (empty input)
"""

import asyncio

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage

from kube_sentinel.agent.chat_service import ChatService
from kube_sentinel.agent.errors import ChatStreamError


PASS = "✅ PASS"
FAIL = "❌ FAIL"


def header(title: str) -> None:
    print(f"\n{'=' * 60}")
    print(f"  {title}")
    print(f"{'=' * 60}")


async def check_multi_turn_context() -> bool:
    """Manual check 4: Multi-turn context retention."""
    header("CHECK 1 — Multi-turn context retention")
    service = ChatService()

    print("\n[Turn 1] Sending: 'My name is Bedirhan.'")
    full_response_1 = ""
    async for token in service.stream("My name is Bedirhan."):
        print(token, end="", flush=True)
        full_response_1 += token
    print()

    print("\n[Turn 2] Sending: 'What is my name?'")
    full_response_2 = ""
    async for token in service.stream("What is my name?"):
        print(token, end="", flush=True)
        full_response_2 += token
    print()

    history = await service.get_chat_history()
    history_valid = (
        len(history) == 5
        and isinstance(history[0], SystemMessage)
        and isinstance(history[1], HumanMessage)
        and isinstance(history[2], AIMessage)
        and isinstance(history[3], HumanMessage)
        and isinstance(history[4], AIMessage)
    )
    name_retained = "bedirhan" in full_response_2.lower()

    print(f"\nHistory structure valid (5 messages): {'✅' if history_valid else '❌'}")
    print(f"Name retained in second response:     {'✅' if name_retained else '❌'}")

    result = history_valid and name_retained
    print(f"\nResult: {PASS if result else FAIL}")
    return result


async def check_reset_behavior() -> bool:
    """Manual check 5: Reset/new chat clears context."""
    header("CHECK 2 — Reset behavior")
    service = ChatService()

    print("\n[Before reset] Sending: 'Hello'")
    async for token in service.stream("Hello"):
        print(token, end="", flush=True)
    print()

    history_before = await service.get_chat_history()
    print(f"\nHistory length before reset: {len(history_before)} (expected 3)")

    print("\n[Resetting conversation...]")
    await service.clear_chat_history()

    history_after = await service.get_chat_history()
    print(f"History length after reset:  {len(history_after)} (expected 1)")

    reset_valid = (
        len(history_after) == 1
        and isinstance(history_after[0], SystemMessage)
    )

    print(f"\nHistory reset to system message only: {'✅' if reset_valid else '❌'}")
    print(f"\nResult: {PASS if reset_valid else FAIL}")
    return reset_valid


async def check_error_recovery() -> bool:
    """Manual check 6: Interrupted/failed stream recovers correctly."""
    header("CHECK 3 — Error recovery (empty input)")
    service = ChatService()

    error_raised = False
    try:
        async for _ in service.stream(""):
            pass
    except ChatStreamError as e:
        error_raised = True
        print(f"\nChatStreamError raised as expected: '{e}'")

    history = await service.get_chat_history()
    history_clean = (
        len(history) == 1
        and isinstance(history[0], SystemMessage)
    )

    print(f"Error raised on empty input:   {'✅' if error_raised else '❌'}")
    print(f"History unaffected after error: {'✅' if history_clean else '❌'}")

    result = error_raised and history_clean
    print(f"\nResult: {PASS if result else FAIL}")
    return result


async def main() -> None:
    print("\n🔍 M1 Manual Validation — Kube-Sentinel ChatService")

    results = {
        "Multi-turn context retention": await check_multi_turn_context(),
        "Reset behavior":               await check_reset_behavior(),
        "Error recovery":               await check_error_recovery(),
    }

    header("SUMMARY")
    all_passed = True
    for check, passed in results.items():
        status = PASS if passed else FAIL
        print(f"  {status}  {check}")
        if not passed:
            all_passed = False

    print(f"\n{'M1 manual checks: ALL PASSED ✅' if all_passed else 'M1 manual checks: FAILURES DETECTED ❌'}\n")


if __name__ == "__main__":
    asyncio.run(main())