"""Shared state schema for the LangGraph orchestration graph."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from langchain_core.messages import BaseMessage
from langgraph.graph import MessagesState


class AgentType(str, Enum):
    COMMS = "comms"
    DATA = "data"
    BUILDER = "builder"
    SOLUTIONS = "solutions"


class ActionStatus(str, Enum):
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
    EXECUTED = "executed"


@dataclass
class PendingAction:
    """An action that requires human approval before execution."""

    id: str
    agent: AgentType
    description: str
    action_type: str  # e.g. "slack_message", "github_pr", "email_send"
    payload: dict[str, Any] = field(default_factory=dict)
    status: ActionStatus = ActionStatus.PENDING
    human_feedback: str = ""


class AgentState(MessagesState):
    """Shared state flowing through the LangGraph graph.

    Extends MessagesState to get built-in message list handling.
    """

    # Task routing
    current_task: str = ""
    target_agent: AgentType | None = None

    # Agent outputs
    agent_outputs: dict[str, Any] = {}

    # Human-in-the-loop
    pending_actions: list[PendingAction] = []
    human_decision: str | None = None  # "approve" | "reject" | feedback text

    # Context
    context: dict[str, Any] = {}  # Shared context (e.g. current project, recent briefing)
