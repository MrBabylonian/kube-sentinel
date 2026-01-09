import asyncio
import sys
import uuid
from typing import Any

import structlog
import typer
from dotenv import load_dotenv
from langchain_core.messages import HumanMessage
from rich.console import Console
from rich.json import JSON
from rich.prompt import Confirm

# Try importing uvloop for performance (Linux/Mac only)
try:
    import uvloop
except ImportError:
    uvloop = None

from kube_sentinel.agent.graph import build_graph
from kube_sentinel.domain.schemas import SreAgentState
from kube_sentinel.k8s.client import K8sClient
from kube_sentinel.utils.logger import setup_logging

load_dotenv()

app = typer.Typer()
console = Console()
logger = structlog.getLogger()


async def run_agent_loop(namespace: str, user_intent: str) -> None:
    """
    The Main Async Event Loop.
    Executes the agent graph and handles Human-in-the-Loop approvals.
    """
    # 1. Build the Graph
    graph = build_graph()

    # 2. Config for Memory (Required for checkpointer)
    thread_id = str(uuid.uuid4())
    config = {"configurable": {"thread_id": thread_id}}

    # 3. Initialize State with USER INTENT
    initial_state: SreAgentState = {
        "messages": [HumanMessage(content=user_intent)],
        "namespace": namespace,
        "diagnosis": None,
        "remediation_plan": None,
        "dry_run_passed": False,
        "user_approval": False,
    }

    console.print(
        f"[bold green]🚀 KubeSentinel Initialized (Namespace: {namespace})[/bold green]"
    )
    console.print(f"[dim]Session ID: {thread_id}[/dim]")
    console.print(f"[dim]Goal: {user_intent}[/dim]\n")

    try:
        # 4. Run the Graph (First Pass)
        async for event in graph.astream(
            initial_state, config=config, stream_mode="values"
        ):
            if event.get("messages"):
                last_msg = event["messages"][-1]

                # Check for tool_calls safely
                has_tool_calls = getattr(last_msg, "tool_calls", None)

                # Print Agent thought process (ignoring tool calls to keep CLI clean)
                if (
                    hasattr(last_msg, "content")
                    and last_msg.content
                    and not has_tool_calls
                ):
                    console.print(
                        f"\n[blue]🤖 Agent:[/blue] {last_msg.content}"
                    )

        # 5. Check for Interrupts (Human-in-the-Loop)
        # FIX: Use aget_state (Async) instead of get_state (Sync)
        snapshot = await graph.aget_state(config)

        if snapshot.next and "remediate" in snapshot.next:
            # We are paused! Get the plan from the state memory.
            current_values = snapshot.values
            plan = current_values.get("remediation_plan")

            if plan:
                console.print("\n[bold red]🛑 APPROVAL REQUIRED[/bold red]")
                console.print(f"[bold]Target:[/bold] {plan.resource_name}")
                console.print(f"[bold]Action:[/bold] {plan.description}")
                console.print(f"[bold]Risk:[/bold] {plan.risk_level}")

                console.print("\n[bold]Verified Patch (JSON):[/bold]")
                console.print(JSON.from_data(plan.patch_json))

                # 6. Authorize and Resume
                if Confirm.ask("\nDo you authorize this remediation?"):
                    console.print("[green]✅ Approved. Resuming...[/green]")

                    # FIX: Use aupdate_state (Async) instead of update_state
                    await graph.aupdate_state(config, {"user_approval": True})

                    # Resume execution
                    async for event in graph.astream(
                        None, config=config, stream_mode="values"
                    ):
                        if event.get("messages"):
                            last_msg = event["messages"][-1]
                            if hasattr(
                                last_msg, "content"
                            ) and "Remediation executed" in str(
                                last_msg.content
                            ):
                                console.print(
                                    f"\n[bold green]🎉 {last_msg.content}[/bold green]"
                                )
                else:
                    console.print("[red]❌ Denied. Exiting.[/red]")

    finally:
        # Cleanup K8s connections (Guaranteed execution)
        await K8sClient().close()


@app.command()
def run(
    namespace: str = typer.Option("default", help="Namespace to monitor"),
    verbose: bool = typer.Option(False, help="Show detailed logs"),
    prompt: str = typer.Option(
        None, help="The initial instruction for the Agent."
    ),
) -> None:
    """
    Start the Autonomous SRE Agent.
    """
    log_level = "DEBUG" if verbose else "INFO"
    setup_logging(level=log_level)

    # 1. Get User Intent (Interactive if not provided via flag)
    if not prompt:
        prompt = typer.prompt(
            "What should the Agent do?",
            default=f"Scan namespace '{namespace}' for issues and fix them",
        )

    # 2. Setup Loop
    runner_kwargs: dict[str, Any] = {}
    if uvloop is not None and sys.platform != "win32":
        logger.debug("uvloop_enabled")
        runner_kwargs["loop_factory"] = uvloop.new_event_loop
    else:
        logger.debug("uvloop_disabled", reason="windows_or_missing_lib")

    # 3. Run
    try:
        asyncio.run(run_agent_loop(namespace, prompt), **runner_kwargs)
    except KeyboardInterrupt:
        console.print("\n[yellow]Agent stopped by user.[/yellow]")


if __name__ == "__main__":
    app()
