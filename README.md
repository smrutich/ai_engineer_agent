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
# Required for v1:
#   - OPENAI_API_KEY
#   - ANTHROPIC_API_KEY
#   - SLACK_BOT_TOKEN + SLACK_APP_TOKEN + SLACK_USER_ID
#   - GITHUB_TOKEN
#
# Optional (enable when integrations are ready):
#   - MS_GRAPH_* (Outlook/Calendar)
#   - JIRA_* (ticket tracking)
#   - SNOWFLAKE_* (data agent)
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

---

## Appendix A: Production Risks & Mitigations

### 1. State & Memory

| Risk | Impact | Fix |
|------|--------|-----|
| MemorySaver is in-memory only | All state lost on restart — pending actions, history gone | Replace with `SqliteSaver` or `PostgresSaver` |
| No message pruning | Message list grows unbounded → context overflow → crashes/high cost | Sliding window + summarization of older messages |
| Mutable default dicts in state | Shared mutable defaults can cause subtle bugs across invocations | Verify LangGraph handles this or use explicit factory patterns |

### 2. LLM Reliability

| Risk | Impact | Fix |
|------|--------|-----|
| No retries on LLM API calls | Transient 429/500/timeout kills the whole run | Add `max_retries=3`, `timeout=60` to LLM constructors |
| ReAct loop has no wall-clock timeout | Agent loops forever if LLM keeps calling tools | Add 2-min timeout alongside `max_iterations` |
| Router returns unexpected text | Falls back silently to comms if GPT says "communications" | Fuzzy matching or structured output |
| No cost tracking | Runaway loops rack up bills silently | Token counting per invocation, budget limits, alerts |

### 3. Security

| Risk | Impact | Fix |
|------|--------|-----|
| Secrets in plain `.env` | Key leaks if repo shared | Use a secret manager (1Password CLI, AWS SM, `keyring`) |
| `_execute_action` passes payload as `**kwargs` | LLM-crafted payloads could inject unexpected args | Validate payload schema; whitelist allowed keys per action type |
| No input sanitization on Slack messages | LLM could generate `@here`/`@channel` or malicious links | Strip dangerous patterns before sending |
| GitHub token has broad access | Compromise = full repo access | Use fine-grained PAT with minimal scopes; rotate regularly |

### 4. API Rate Limits & Resilience

| Risk | Impact | Fix |
|------|--------|-----|
| No rate limiting on Slack calls | 50+ channels hits Slack Tier 3 limit (50 req/min) | Add `time.sleep(1)` between fetches or batch with pagination |
| `conversations_list` doesn't paginate | Only returns first ~100 channels | Follow `response_metadata.next_cursor` |
| No HTTP timeout on httpx calls | Hanging API → frozen agent | Add `timeout=30` to all httpx requests |
| No circuit breaker | If Slack is down, every cron run fails immediately | Exponential backoff; skip if last attempt was <5 min ago |

### 5. Observability

| Risk | Impact | Fix |
|------|--------|-----|
| No logging | No way to debug production failures | Add `structlog` with context (agent name, task ID, timestamp) |
| No tracing | Can't see tool calls, durations, token usage | Enable LangSmith tracing or OpenTelemetry |
| Silent tool failures | Tools return error strings; agent may ignore them | Log at WARNING; add metrics on tool failure rate |
| No health check | Cron runs silently; no visibility | Add `ai-engineer health` command to verify all API connections |

### 6. Concurrency & Data Integrity

| Risk | Impact | Fix |
|------|--------|-----|
| Single thread_id "main" in CLI | Multiple invocations stomp on each other's state | Unique thread IDs per session |
| Pending actions not persisted to disk | Process crash between creation and approval = lost actions | Persist to SQLite/JSON immediately |
| No locking on cron vs CLI | Simultaneous runs on same thread cause corruption | File-based lock or separate thread IDs per context |

### 7. LLM Output Parsing

| Risk | Impact | Fix |
|------|--------|-----|
| `_extract_pending_actions` uses string matching | LLM may phrase drafts differently → missed actions | Use structured output (JSON mode or tool-based proposals) |
| Builder uses `[CREATE PR]` detection | Same brittleness | Agents return structured `PendingAction` via dedicated tool |
| No validation on tool call arguments | LLM could pass wrong types/missing fields | Add Pydantic validation on critical tools |

### 8. Token/Context Management

| Risk | Impact | Fix |
|------|--------|-----|
| Full Slack history passed to LLM | 50 msgs × 50 channels = massive token burn | Limit to 5-10 channels; summarize before LLM call |
| PR diffs truncated at 10000 chars | May miss important changes at end of diff | Summarize diffs with a separate LLM call |
| No token counting before invocation | May exceed context window → API error | Count with `tiktoken` before invoking; trim if over |

### Priority Order

1. **Immediate** (will cause outages): Persistent checkpointer, LLM retries + timeouts, HTTP timeouts, logging
2. **Soon** (data loss / surprise bills): Message pruning, rate limiting, cost tracking, persistent pending actions
3. **Hardening** (security & reliability): Payload validation, structured output, health checks, circuit breakers

---

## Appendix B: Agent-to-Agent Communication & Memory Architecture

### Current Limitations

```
User → Router → ONE agent → Response (no cross-agent context)
```

- **No A2A handoff**: Router picks one agent; it can't delegate sub-tasks to another
- **No shared memory**: In-memory checkpointer; everything lost on restart
- **No context passing**: `context: dict` in state is defined but never used
- **`agent_outputs` is write-only**: Each agent writes, no agent reads another's output

### Target Architecture

```
┌─────────────────────────────────────────────────────────┐
│                    MEMORY LAYERS                         │
├─────────────────────────────────────────────────────────┤
│                                                         │
│  ┌─────────────┐  ┌──────────────┐  ┌──────────────┐  │
│  │   Working   │  │   Session    │  │   Long-term  │  │
│  │   Memory    │  │   Store      │  │   (Vector)   │  │
│  │             │  │              │  │              │  │
│  │ agent_outputs│  │ SQLite/PG   │  │ ChromaDB/    │  │
│  │ within turn │  │ checkpoints  │  │ Pinecone     │  │
│  └──────┬──────┘  └──────┬───────┘  └──────┬───────┘  │
│         │                │                 │           │
│         └────────────────┼─────────────────┘           │
│                          │                             │
│              All agents read/write                      │
└─────────────────────────────────────────────────────────┘
```

### A2A Pattern 1: Loop-Back Graph (Sequential Handoff)

After each agent finishes, the router re-evaluates if another agent should contribute:

```python
# Graph with loop-back:
Router → Agent → needs_followup? ─── yes ──→ Router (loop back)
                       │
                       no → END
```

Example: "Check Slack for data requests and build dbt models for them"
1. Router → comms agent (finds the request in Slack)
2. Loop back → Router → data agent (builds the dbt model using comms output)
3. Done

### A2A Pattern 2: Agent-as-Tool (Nested Delegation)

One agent calls another as a tool within its ReAct loop:

```python
@tool
def delegate_to_data_agent(task: str) -> str:
    """Ask the data agent to handle a sub-task."""
    from src.agents.data import run_data_agent
    result = run_data_agent({"messages": [HumanMessage(content=task)]})
    return result["messages"][-1].content
```

### A2A Pattern 3: Context Injection (Read Other Agents' Output)

Before calling any agent, inject what other agents have already produced:

```python
# In each agent's run function:
prior_context = state.get("agent_outputs", {})
if prior_context:
    context_msg = SystemMessage(
        content=f"Context from prior agents:\n{json.dumps(prior_context, indent=2)}"
    )
    messages.insert(1, context_msg)
```

### Memory Layers Explained

| Layer | Scope | Storage | Use Case |
|-------|-------|---------|----------|
| **Working memory** | Single turn | `agent_outputs` in state | Agent B reads what Agent A just produced |
| **Session memory** | One conversation thread | SQLite checkpointer | Resume after approval; "what did I ask earlier?" |
| **Long-term memory** | Across all sessions | Vector store (ChromaDB) | "What did we decide about the orders pipeline last week?" |
| **Entity memory** | Per entity (project, person, ticket) | Structured key-value store | Track facts: "PROJ-123 needs dbt model, deadline Friday" |

### Implementation Priority

1. **Context injection** — agents see each other's outputs within a turn (minimal code change)
2. **SQLite checkpointer** — sessions persist across restarts
3. **Loop-back graph** — enables multi-agent collaboration on complex tasks
4. **Vector store** — long-term semantic memory for cross-session retrieval
5. **Entity memory** — structured facts about recurring entities
