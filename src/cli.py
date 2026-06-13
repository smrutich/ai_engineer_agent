"""CLI entry point for the AI Engineer Agent system.

Commands:
    ai-engineer briefing        — Run the comms agent for a daily summary
    ai-engineer task "<desc>"   — Route a task to the appropriate agent
    ai-engineer approve         — Review and approve/reject pending actions
    ai-engineer status          — Show agent states and recent outputs
    ai-engineer schedule        — Show configured cron schedules
"""

from __future__ import annotations

import json
from pathlib import Path

import typer
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.markdown import Markdown

from langchain_core.messages import HumanMessage

from src.config import settings
from src.graph import app as graph
from src.state import ActionStatus

app = typer.Typer(name="ai-engineer", help="AI Engineer Multi-Agent System")
console = Console()

# Thread config for LangGraph checkpointing
DEFAULT_THREAD = {"configurable": {"thread_id": "main"}}


@app.command()
def briefing(hours_back: int = typer.Option(24, help="Hours to look back")):
    """Generate a daily briefing from all communication channels."""
    console.print(Panel("[bold]Daily Briefing[/bold]", style="blue"))
    console.print("Checking Slack, Outlook, and Jira...\n")

    input_msg = HumanMessage(
        content=f"Generate my daily briefing. Check all channels for the last {hours_back} hours. "
        "Organize by: (1) Urgent/action-needed items, (2) FYI/updates, (3) Upcoming meetings/deadlines."
    )

    result = graph.invoke({"messages": [input_msg]}, config=DEFAULT_THREAD)

    # Display the result
    final_msg = result["messages"][-1]
    console.print(Markdown(final_msg.content))

    # Check for pending actions
    pending = [a for a in result.get("pending_actions", []) if a.status == ActionStatus.PENDING]
    if pending:
        console.print(f"\n[yellow]⚠ {len(pending)} pending action(s) need approval. Run 'ai-engineer approve'.[/yellow]")


@app.command()
def task(description: str = typer.Argument(..., help="Task description")):
    """Route a task to the appropriate specialist agent."""
    console.print(Panel(f"[bold]Task:[/bold] {description}", style="green"))

    input_msg = HumanMessage(content=description)
    result = graph.invoke({"messages": [input_msg]}, config=DEFAULT_THREAD)

    # Display which agent handled it
    target = result.get("target_agent")
    if target:
        console.print(f"[dim]Routed to: {target.value} agent[/dim]\n")

    final_msg = result["messages"][-1]
    console.print(Markdown(final_msg.content))

    # Check for pending actions
    pending = [a for a in result.get("pending_actions", []) if a.status == ActionStatus.PENDING]
    if pending:
        console.print(f"\n[yellow]⚠ {len(pending)} pending action(s) need approval. Run 'ai-engineer approve'.[/yellow]")


@app.command()
def approve():
    """Review and approve/reject pending actions."""
    actions_path = Path(settings.pending_actions_path)

    # Get current state from checkpointer
    state = graph.get_state(DEFAULT_THREAD)
    pending = [a for a in state.values.get("pending_actions", []) if a.status == ActionStatus.PENDING]

    if not pending:
        console.print("[green]No pending actions to review.[/green]")
        return

    console.print(Panel(f"[bold]{len(pending)} Pending Action(s)[/bold]", style="yellow"))

    table = Table(show_header=True)
    table.add_column("#", width=3)
    table.add_column("Agent", width=10)
    table.add_column("Type", width=15)
    table.add_column("Description")

    for i, action in enumerate(pending, 1):
        table.add_row(str(i), action.agent.value, action.action_type, action.description)

    console.print(table)
    console.print()

    decision = typer.prompt(
        "Enter 'approve' to execute all, 'reject' to cancel, or feedback text"
    )

    # Resume the graph with the human decision
    graph.update_state(DEFAULT_THREAD, {"human_decision": decision})
    result = graph.invoke(None, config=DEFAULT_THREAD)

    final_msg = result["messages"][-1]
    console.print(f"\n{final_msg.content}")


@app.command()
def status():
    """Show current system status and recent outputs."""
    console.print(Panel("[bold]System Status[/bold]", style="blue"))

    state = graph.get_state(DEFAULT_THREAD)
    values = state.values if state else {}

    # Agent outputs
    outputs = values.get("agent_outputs", {})
    if outputs:
        for agent_name, output in outputs.items():
            console.print(f"\n[bold]{agent_name.upper()} Agent:[/bold]")
            console.print(output[:500] if output else "No output")
    else:
        console.print("[dim]No recent agent outputs.[/dim]")

    # Pending actions
    pending = [a for a in values.get("pending_actions", []) if a.status == ActionStatus.PENDING]
    if pending:
        console.print(f"\n[yellow]{len(pending)} pending action(s) awaiting approval.[/yellow]")


@app.command()
def schedule():
    """Show configured schedules and cron jobs."""
    console.print(Panel("[bold]Configured Schedules[/bold]", style="blue"))

    schedules = [
        ("Every 30 min", "Check Slack mentions + Outlook inbox"),
        ("Daily 8:00 AM", "Generate full daily briefing"),
        ("Daily 6:00 PM", "End-of-day summary and pending items"),
    ]

    table = Table(show_header=True)
    table.add_column("Schedule", width=15)
    table.add_column("Task")

    for sched, desc in schedules:
        table.add_row(sched, desc)

    console.print(table)
    console.print("\n[dim]Use system cron or launchd to configure these schedules.[/dim]")


@app.command()
def chat():
    """Interactive chat mode — have a back-and-forth conversation with the AI Engineer."""
    import uuid

    thread_id = f"chat-{uuid.uuid4().hex[:8]}"
    thread_config = {"configurable": {"thread_id": thread_id}}

    console.print(Panel("[bold]AI Engineer — Interactive Chat[/bold]", style="cyan"))
    console.print("[dim]Type your messages below. Commands:[/dim]")
    console.print("[dim]  /quit or /exit  — end the session[/dim]")
    console.print("[dim]  /approve        — approve pending actions[/dim]")
    console.print("[dim]  /status         — show agent status[/dim]")
    console.print()

    while True:
        try:
            user_input = console.input("[bold green]you>[/bold green] ").strip()
        except (KeyboardInterrupt, EOFError):
            console.print("\n[dim]Session ended.[/dim]")
            break

        if not user_input:
            continue

        if user_input.lower() in ("/quit", "/exit", "quit", "exit"):
            console.print("[dim]Session ended.[/dim]")
            break

        if user_input.lower() == "/approve":
            _handle_approve(thread_config)
            continue

        if user_input.lower() == "/status":
            _handle_status(thread_config)
            continue

        # Send to graph
        input_msg = HumanMessage(content=user_input)
        try:
            result = graph.invoke({"messages": [input_msg]}, config=thread_config)

            # Show which agent handled it
            target = result.get("target_agent")
            if target:
                console.print(f"[dim]  [{target.value} agent][/dim]")

            final_msg = result["messages"][-1]
            console.print()
            console.print(Markdown(final_msg.content))
            console.print()

            # Notify about pending actions
            pending = [a for a in result.get("pending_actions", []) if a.status == ActionStatus.PENDING]
            if pending:
                console.print(f"[yellow]⚠ {len(pending)} pending action(s). Type /approve to review.[/yellow]\n")

        except Exception as e:
            console.print(f"[red]Error: {e}[/red]\n")


def _handle_approve(thread_config: dict):
    """Handle inline approval during chat."""
    state = graph.get_state(thread_config)
    if not state or not state.values:
        console.print("[dim]No state available.[/dim]\n")
        return

    pending = [a for a in state.values.get("pending_actions", []) if a.status == ActionStatus.PENDING]
    if not pending:
        console.print("[green]No pending actions.[/green]\n")
        return

    table = Table(show_header=True)
    table.add_column("#", width=3)
    table.add_column("Agent", width=10)
    table.add_column("Type", width=15)
    table.add_column("Description")

    for i, action in enumerate(pending, 1):
        table.add_row(str(i), action.agent.value, action.action_type, action.description)

    console.print(table)
    decision = console.input("[bold yellow]approve/reject>[/bold yellow] ").strip()

    graph.update_state(thread_config, {"human_decision": decision})
    result = graph.invoke(None, config=thread_config)
    final_msg = result["messages"][-1]
    console.print(f"{final_msg.content}\n")


def _handle_status(thread_config: dict):
    """Show status during chat."""
    state = graph.get_state(thread_config)
    if not state or not state.values:
        console.print("[dim]No activity yet.[/dim]\n")
        return

    outputs = state.values.get("agent_outputs", {})
    if outputs:
        for agent_name, output in outputs.items():
            console.print(f"[bold]{agent_name}:[/bold] {(output or '')[:200]}")
    else:
        console.print("[dim]No agent outputs yet.[/dim]")
    console.print()


if __name__ == "__main__":
    app()
