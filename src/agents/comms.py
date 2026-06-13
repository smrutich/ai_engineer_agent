"""Communications Agent — handles Slack, Outlook, and Jira interactions.

Responsible for:
- Polling Slack channels for mentions and DMs
- Reading Outlook inbox for emails and meeting invites
- Checking Jira for assigned tickets and updates
- Producing daily briefings
- Drafting replies (held for human approval)
"""

from __future__ import annotations

import uuid
from typing import Any

from langchain_anthropic import ChatAnthropic
from langchain_core.messages import AIMessage, SystemMessage
from langchain_core.tools import tool

from src.config import settings
from src.state import ActionStatus, AgentState, AgentType, PendingAction


COMMS_SYSTEM_PROMPT = """You are the Communications Agent for an AI Engineer.
Your job is to monitor and summarize communications across Slack, Outlook, and Jira.

You can:
1. Check Slack for mentions, DMs, and relevant channel activity
2. Check Outlook for unread emails and upcoming calendar events
3. Check Jira for assigned tickets and updates
4. Produce daily briefings summarizing priorities
5. Draft replies to messages/emails (these will be queued for human approval)

IMPORTANT RULES:
- Always call check_slack_mentions first to see direct mentions.
- For check_slack_messages, pass channel_ids=None to auto-discover all channels. Do NOT ask the user for channel IDs.
- Any action that sends an external message (Slack, email) must be returned as a pending_action for human approval.
- Read-only operations (checking messages) can proceed directly.
- When creating briefings, organize by priority: urgent items first, then FYI items.
- When drafting replies, be professional and concise.
"""


@tool
def check_slack_mentions(hours_back: int = 24) -> str:
    """Check Slack for recent mentions of the user."""
    from src.tools.slack import get_mentions
    try:
        mentions = get_mentions(hours_back=hours_back)
        if not mentions:
            return f"No new Slack mentions in the last {hours_back} hours."
        if "error" in mentions[0]:
            return f"Slack API error: {mentions[0]['error']}"
        lines = [f"Found {len(mentions)} mention(s):"]
        for m in mentions:
            lines.append(f"  - From {m.get('user', 'unknown')}: {m.get('text', '')[:100]}")
        return "\n".join(lines)
    except Exception as e:
        return f"Error checking Slack mentions: {e}"


@tool
def check_slack_messages(channel_ids: list[str] | None = None, hours_back: int = 24) -> str:
    """Check recent messages in Slack channels. Pass None for channel_ids to auto-discover all channels."""
    from src.tools.slack import get_unread_messages
    try:
        messages = get_unread_messages(channel_ids=channel_ids, hours_back=hours_back)
        if not messages:
            return "No new messages."
        if "error" in messages[0]:
            return f"Slack API error: {messages[0]['error']}"
        lines = [f"Found {len(messages)} message(s):"]
        for m in messages[:20]:
            lines.append(f"  [{m.get('channel', '?')}] {m.get('user', 'unknown')}: {m.get('text', '')[:80]}")
        return "\n".join(lines)
    except Exception as e:
        return f"Error checking Slack messages: {e}"


@tool
def check_outlook_inbox(unread_only: bool = True) -> str:
    """Check Outlook inbox for recent emails."""
    from src.tools.outlook import get_recent_emails
    try:
        emails = get_recent_emails(top=10, unread_only=unread_only)
        if not emails:
            return "No unread emails."
        lines = [f"Found {len(emails)} unread email(s):"]
        for e in emails:
            lines.append(f"  - From {e['from']}: {e['subject']} ({e['received'][:10]})")
            if e['preview']:
                lines.append(f"    Preview: {e['preview'][:100]}...")
        return "\n".join(lines)
    except RuntimeError:
        return "Outlook client not initialized. OAuth token needed."


@tool
def check_calendar(days_ahead: int = 3) -> str:
    """Check upcoming calendar events."""
    from src.tools.outlook import get_calendar_events
    try:
        events = get_calendar_events(days_ahead=days_ahead)
        if not events:
            return "No upcoming events."
        lines = [f"Found {len(events)} upcoming event(s):"]
        for e in events:
            lines.append(f"  - {e['subject']} ({e['start'][:16]}) - Organizer: {e['organizer']}")
        return "\n".join(lines)
    except RuntimeError:
        return "Outlook client not initialized. OAuth token needed."


@tool
def check_jira_tickets(status: str | None = None) -> str:
    """Check Jira tickets assigned to the user."""
    from src.tools.jira import get_my_tickets
    tickets = get_my_tickets(status=status)
    if not tickets:
        return "No assigned tickets found."
    lines = [f"Found {len(tickets)} ticket(s):"]
    for t in tickets:
        lines.append(f"  [{t['key']}] {t['summary']} — Status: {t['status']}, Priority: {t['priority']}")
    return "\n".join(lines)


def get_comms_tools() -> list:
    """Build tool list based on which integrations are configured."""
    from src.config import settings
    tools = [check_slack_mentions, check_slack_messages]
    if settings.outlook.is_configured:
        tools.extend([check_outlook_inbox, check_calendar])
    if settings.jira.is_configured:
        tools.append(check_jira_tickets)
    return tools


def run_comms_agent(state: AgentState) -> dict:
    """Execute the communications agent."""
    tools = get_comms_tools()
    llm = ChatAnthropic(
        model=settings.llm.summarization_model,
        api_key=settings.llm.anthropic_api_key,
    )
    llm_with_tools = llm.bind_tools(tools)

    messages = [SystemMessage(content=COMMS_SYSTEM_PROMPT)] + list(state["messages"])

    # ReAct loop — let the agent call tools iteratively
    max_iterations = 8
    for _ in range(max_iterations):
        response = llm_with_tools.invoke(messages)
        messages.append(response)

        if not response.tool_calls:
            break

        # Execute tool calls
        from langchain_core.messages import ToolMessage
        for tc in response.tool_calls:
            tool_fn = next((t for t in tools if t.name == tc["name"]), None)
            if tool_fn:
                result = tool_fn.invoke(tc["args"])
                messages.append(ToolMessage(content=str(result), tool_call_id=tc["id"]))

    # Check if the agent wants to draft any external messages
    pending_actions = _extract_pending_actions(response.content, state)

    return {
        "messages": [AIMessage(content=response.content)],
        "pending_actions": state.get("pending_actions", []) + pending_actions,
        "agent_outputs": {**state.get("agent_outputs", {}), "comms": response.content},
    }


def _extract_pending_actions(agent_response: str, state: AgentState) -> list[PendingAction]:
    """Parse the agent response for any proposed external actions."""
    actions = []
    # The agent is instructed to format actions clearly
    # In production, use structured output; for now, detect patterns
    if "[DRAFT REPLY]" in agent_response or "[SEND MESSAGE]" in agent_response:
        actions.append(
            PendingAction(
                id=str(uuid.uuid4()),
                agent=AgentType.COMMS,
                description="Draft message detected in agent response — needs review",
                action_type="slack_message",
                payload={"text": agent_response},
            )
        )
    return actions
