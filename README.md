# AI Engineer Agent

A multi-agent system that acts as an AI Engineer — monitoring communications, modeling data, building POCs, and architecting solutions. Built with LangGraph for stateful orchestration and human-in-the-loop approval.

## Architecture

```
┌─────────────────────────────────────────────────────────┐
│                   ORCHESTRATOR (LangGraph)               │
│                                                         │
│   User Task ──→ Router ──→ Specialist Agent ──→ Review  │
│                                                         │
│   ┌─────────────────────────────────────────────────┐   │
│   │            SHARED STATE (checkpointed)          │   │
│   └─────────────────────────────────────────────────┘   │
└───────────┬───────────┬───────────┬───────────┬─────────┘
            │           │           │           │
     ┌──────┴──┐  ┌─────┴───┐  ┌───┴────┐  ┌──┴───────┐
     │  Comms  │  │  Data   │  │Builder │  │Solutions │
     │  Agent  │  │  Agent  │  │ Agent  │  │  Agent   │
     └─────────┘  └─────────┘  └────────┘  └──────────┘
      Slack         Snowflake    GitHub       Architecture
      Outlook       dbt          Code Gen     Design Docs
      Jira          Profiling    Testing      ADRs
```

## Agents

| Agent | LLM | Responsibilities |
|-------|-----|-----------------|
| **Communications** | Claude (long-context) | Slack mentions, Outlook inbox, Jira tickets, daily briefings, draft replies |
| **Data** | GPT-4o | SQL queries, dbt model generation, data profiling, Snowflake Cortex AI |
| **Builder** | GPT-4o | Code generation, POC scaffolding, GitHub PRs/issues, testing |
| **Solutions** | Claude (reasoning) | Architecture design, ADRs, tech evaluations, PR review, Mermaid diagrams |

## How It Works

### 1. Task Routing
Every request enters through the **Router** node, which classifies it and dispatches to the appropriate specialist agent. The router uses a lightweight model (GPT-4o-mini) for fast classification.

### 2. Agent Execution
Each agent runs a ReAct loop — reasoning about the task, calling tools, and iterating until it produces a result. Agents have access to specific tool sets matching their domain.

### 3. Human-in-the-Loop Approval
Any action with external side effects (sending a Slack message, creating a PR, sending an email) is **queued as a pending action**. The system pauses and waits for human approval before executing.

```
Agent drafts action → Pending queue → Human reviews → Approve/Reject → Execute
```

### 4. Scheduled Automation
Cron jobs handle recurring tasks without manual invocation:

| Schedule | Task |
|----------|------|
| Every 30 min | Check Slack mentions + urgent emails |
| Daily 8:00 AM | Full morning briefing |
| Daily 6:00 PM | End-of-day summary |

## CLI Usage

```bash
# Generate a daily briefing from all channels
ai-engineer briefing

# Route a task to the appropriate agent
ai-engineer task "design a dbt model for customer orders"
ai-engineer task "review PR #42 on our data-pipeline repo"
ai-engineer task "scaffold a FastAPI POC for the recommendation engine"
ai-engineer task "check my Jira board for blockers"

# Review and approve/reject pending actions
ai-engineer approve

# Check system status and recent outputs
ai-engineer status

# View configured schedules
ai-engineer schedule
```

## Setup

### 1. Install

```bash
pip install -e .
```

### 2. Configure

```bash
cp .env.example .env
# Fill in your API keys:
#   - OPENAI_API_KEY
#   - ANTHROPIC_API_KEY
#   - SLACK_BOT_TOKEN + SLACK_USER_ID
#   - MS_GRAPH_CLIENT_ID/SECRET/TENANT_ID (for Outlook)
#   - GITHUB_TOKEN
#   - JIRA_BASE_URL + JIRA_EMAIL + JIRA_API_TOKEN
#   - SNOWFLAKE_* credentials
```

### 3. Configure Cron (optional)

```bash
crontab -e
# Add:
*/30 * * * * cd /path/to/ai_engineer_agent && python -m schedules.cron_jobs quick_check
0 8 * * 1-5  cd /path/to/ai_engineer_agent && python -m schedules.cron_jobs morning_briefing
0 18 * * 1-5 cd /path/to/ai_engineer_agent && python -m schedules.cron_jobs eod_summary
```

## Project Structure

```
ai_engineer_agent/
├── pyproject.toml              # Dependencies and CLI entry point
├── .env.example                # Required environment variables
├── src/
│   ├── config.py               # Settings loaded from .env
│   ├── state.py                # LangGraph shared state schema
│   ├── graph.py                # Orchestration graph with routing + interrupts
│   ├── cli.py                  # Typer CLI (briefing, task, approve, status)
│   ├── agents/
│   │   ├── comms.py            # Communications agent
│   │   ├── data.py             # Data engineering agent
│   │   ├── builder.py          # Code generation agent
│   │   └── solutions.py       # Solutions architect agent
│   ├── tools/
│   │   ├── slack.py            # Slack SDK wrapper
│   │   ├── outlook.py          # Microsoft Graph API wrapper
│   │   ├── github.py           # GitHub REST API wrapper
│   │   ├── jira.py             # Jira/Linear API wrapper
│   │   ├── snowflake.py        # Snowflake connector + Cortex functions
│   │   └── dbt.py              # dbt CLI wrapper
│   └── prompts/                # System prompts per agent
├── schedules/
│   └── cron_jobs.py            # Cron entry points
└── tests/
```

## Design Decisions

- **LangGraph over CrewAI/AutoGen**: Gives fine-grained control over state, routing, and interrupt/resume patterns needed for human-in-the-loop.
- **Mixed LLMs**: Each agent uses the model best suited to its task — Claude for analysis, GPT-4o for code generation.
- **Human-in-the-loop by default**: No external action fires without explicit approval. Safety over speed.
- **CLI-first**: Fast iteration and scripting-friendly. UI layer (Streamlit) planned for later.
- **Stateful checkpointing**: LangGraph's MemorySaver allows pausing at human review and resuming after approval.

## Roadmap

- [ ] OAuth flow for Microsoft Graph (Outlook/Calendar)
- [ ] Persistent memory via vector store for cross-session context
- [ ] Streamlit dashboard for approval workflow and agent monitoring
- [ ] Slack bot mode (respond to commands directly in Slack)
- [ ] Feedback loop — agents learn from approved/rejected actions
