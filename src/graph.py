"""Main LangGraph orchestration graph for the AI Engineer Agent system.

Implements the routing, agent dispatch, human-in-the-loop approval,
and action execution flow.
"""

from __future__ import annotations

import json
import uuid
from typing import Literal

from langchain_anthropic import ChatAnthropic
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from langchain_openai import ChatOpenAI
from langgraph.graph import END, StateGraph
from langgraph.checkpoint.memory import MemorySaver

from src.config import settings
from src.state import ActionStatus, AgentState, AgentType, PendingAction


# --- LLM Instances ---

def get_router_llm():
    return ChatOpenAI(
        model="gpt-4o-mini",
        api_key=settings.llm.openai_api_key,
        temperature=0,
    )


def get_llm_for_agent(agent_type: AgentType):
    """Return the appropriate LLM based on agent role."""
    match agent_type:
        case AgentType.COMMS:
            return ChatAnthropic(
                model=settings.llm.summarization_model,
                api_key=settings.llm.anthropic_api_key,
            )
        case AgentType.DATA:
            return ChatOpenAI(
                model=settings.llm.sql_model,
                api_key=settings.llm.openai_api_key,
            )
        case AgentType.BUILDER:
            return ChatOpenAI(
                model=settings.llm.code_model,
                api_key=settings.llm.openai_api_key,
            )
        case AgentType.SOLUTIONS:
            return ChatAnthropic(
                model=settings.llm.reasoning_model,
                api_key=settings.llm.anthropic_api_key,
            )


# --- Graph Nodes ---

def router_node(state: AgentState) -> dict:
    """Classify the incoming task and route to the appropriate agent."""
    llm = get_router_llm()

    system_prompt = """You are a task router for an AI Engineer agent system.
Given the user's request, determine which specialist agent should handle it.

Agents:
- comms: Slack messages, emails, Outlook, meeting summaries, daily briefings, Jira/ticket updates
- data: SQL queries, dbt models, data profiling, Snowflake, data transformations, EDA
- builder: Code generation, GitHub PRs, POC scaffolding, testing, building new tools/agents
- solutions: Architecture design, system diagrams, ADRs, tech evaluations, PR reviews for design

Respond with ONLY the agent name (comms, data, builder, or solutions)."""

    messages = [SystemMessage(content=system_prompt)] + state["messages"][-3:]
    response = llm.invoke(messages)
    agent_name = response.content.strip().lower()

    # Map to enum
    agent_map = {
        "comms": AgentType.COMMS,
        "data": AgentType.DATA,
        "builder": AgentType.BUILDER,
        "solutions": AgentType.SOLUTIONS,
    }
    target = agent_map.get(agent_name, AgentType.COMMS)

    return {"target_agent": target, "current_task": state["messages"][-1].content}


def route_to_agent(state: AgentState) -> str:
    """Conditional edge: route to the selected agent node."""
    target = state.get("target_agent", AgentType.COMMS)
    return target.value


def comms_node(state: AgentState) -> dict:
    """Communications agent — handles Slack, Outlook, Jira interactions."""
    from src.agents.comms import run_comms_agent
    return run_comms_agent(state)


def data_node(state: AgentState) -> dict:
    """Data agent — handles SQL, dbt, Snowflake, profiling."""
    from src.agents.data import run_data_agent
    return run_data_agent(state)


def builder_node(state: AgentState) -> dict:
    """Builder agent — handles code gen, GitHub, POC scaffolding."""
    from src.agents.builder import run_builder_agent
    return run_builder_agent(state)


def solutions_node(state: AgentState) -> dict:
    """Solutions agent — handles architecture, design, evaluations."""
    from src.agents.solutions import run_solutions_agent
    return run_solutions_agent(state)


def human_review_node(state: AgentState) -> dict:
    """Present pending actions for human approval.

    This node uses LangGraph's interrupt mechanism — execution pauses here
    and resumes when the human provides a decision.
    """
    pending = [a for a in state.get("pending_actions", []) if a.status == ActionStatus.PENDING]
    if not pending:
        return {"human_decision": "approve"}

    # Format pending actions for display
    summary = "\n".join(
        f"  [{i+1}] ({a.action_type}) {a.description}" for i, a in enumerate(pending)
    )
    return {
        "messages": [
            AIMessage(
                content=f"The following actions need your approval:\n{summary}\n\n"
                "Reply 'approve' to execute all, 'reject' to cancel, "
                "or provide specific feedback."
            )
        ]
    }


def should_review(state: AgentState) -> str:
    """Check if there are pending actions that need human review."""
    pending = [a for a in state.get("pending_actions", []) if a.status == ActionStatus.PENDING]
    if pending:
        return "human_review"
    return "end"


def executor_node(state: AgentState) -> dict:
    """Execute approved actions."""
    decision = state.get("human_decision", "")
    pending = state.get("pending_actions", [])
    results = []

    if decision and decision.lower().startswith("approve"):
        for action in pending:
            if action.status == ActionStatus.PENDING:
                action.status = ActionStatus.APPROVED
                # Dispatch to appropriate tool
                result = _execute_action(action)
                action.status = ActionStatus.EXECUTED
                results.append(f"Executed: {action.description} -> {result}")
    else:
        for action in pending:
            if action.status == ActionStatus.PENDING:
                action.status = ActionStatus.REJECTED
                action.human_feedback = decision or "Rejected without feedback"
        results.append("All pending actions rejected.")

    return {
        "pending_actions": pending,
        "messages": [AIMessage(content="\n".join(results))],
    }


def _execute_action(action: PendingAction) -> str:
    """Dispatch an approved action to the appropriate tool."""
    match action.action_type:
        case "slack_message":
            from src.tools.slack import send_slack_message
            return send_slack_message(**action.payload)
        case "email_send":
            from src.tools.outlook import send_email
            return send_email(**action.payload)
        case "github_pr":
            from src.tools.github import create_pr
            return create_pr(**action.payload)
        case _:
            return f"Unknown action type: {action.action_type}"


# --- Build the Graph ---

def build_graph():
    """Construct and compile the orchestration graph."""
    graph = StateGraph(AgentState)

    # Add nodes
    graph.add_node("router", router_node)
    graph.add_node("comms", comms_node)
    graph.add_node("data", data_node)
    graph.add_node("builder", builder_node)
    graph.add_node("solutions", solutions_node)
    graph.add_node("human_review", human_review_node)
    graph.add_node("executor", executor_node)

    # Set entry point
    graph.set_entry_point("router")

    # Router -> agent (conditional)
    graph.add_conditional_edges(
        "router",
        route_to_agent,
        {
            "comms": "comms",
            "data": "data",
            "builder": "builder",
            "solutions": "solutions",
        },
    )

    # Each agent -> check if needs human review
    for agent in ["comms", "data", "builder", "solutions"]:
        graph.add_conditional_edges(
            agent,
            should_review,
            {"human_review": "human_review", "end": END},
        )

    # Human review -> executor (interrupt happens here)
    graph.add_edge("human_review", "executor")
    graph.add_edge("executor", END)

    # Compile with checkpointing for interrupt/resume
    memory = MemorySaver()
    return graph.compile(checkpointer=memory, interrupt_before=["executor"])


# Singleton graph instance
app = build_graph()
