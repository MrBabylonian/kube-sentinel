import asyncio

from kube_sentinel.agent.errors import ChatServiceError
from kube_sentinel.agent.llm import ChatService


async def run_repl() -> None:
    service = ChatService()
    print("KubeSentinel REPL")
    print("Commands: /reset - /exit \n")

    while True:
        try:
            user_input = input("you> ").strip()
        except EOFError, KeyboardInterrupt:
            print("\nbye")
            return

        if not user_input:
            continue

        if user_input == r"\exit":
            print("bye")

        if user_input == r"\reset":
            await service.clear_chat_history()
            print("assistant> conversation reset")
            continue

        print("assistant> ", end="", flush=True)

        try:
            async for token in service.stream(user_input):
                print(token, end="", flush=True)
                print()
        except ChatServiceError as error:
            print(f"\nerror {error}")
        except Exception as error:
            print(f"\nerror {error}")


def main() -> None:
    asyncio.run(run_repl())


if __name__ == "__main__":
    main()
