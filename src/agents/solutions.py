"""Solutions Agent — handles architecture, design, and technical evaluations.

Responsible for:
- Evaluating technical approaches and trade-offs
- Producing architecture decision records (ADRs)
- Designing system diagrams and data flows
- Reviewing PRs for architecture alignment
- Researching new tools/frameworks
"""

from __future__ import annotations

from langchain_anthropic import ChatAnthropic
from langchain_core.messages import AIMessage, SystemMessage, ToolMessage
from langchain_core.tools import tool
from langchain_openai import ChatOpenAI

from src.config import settings
from src.state import AgentState


SOLUTIONS_SYSTEM_PROMPT = """You are the Solutions Architect Agent for an AI Engineer.
Your job is to design systems, evaluate trade-offs, and ensure architectural quality.

You can:
1. Review PR diffs for architectural concerns
2. Generate Architecture Decision Records (ADRs)
3. Design system diagrams (as structured text/mermaid)
4. Evaluate technology choices with pros/cons
5. Research tools and frameworks

When reviewing architecture:
- Focus on separation of concerns, scalability, and maintainability
- Identify potential single points of failure
- Check for proper error handling and observability
- Verify data flow and security boundaries

When producing ADRs, use this format:
  ## Title
  ## Status (proposed/accepted/deprecated)
  ## Context
  ## Decision
  ## Consequences (positive/negative)

Output diagrams in Mermaid syntax when possible.
"""


@tool
def review_pr_architecture(repo: str, pr_number: int) -> str:
    """Review a PR diff for architectural concerns."""
    from src.tools.github import get_pr_diff
    diff = get_pr_diff(repo, pr_number)
    if not diff:
        return "Could not fetch PR diff."
    return f"PR diff for review (first 5000 chars):\n{diff[:5000]}"


@tool
def get_repo_structure(repo: str) -> str:
    """Get the top-level file structure of a GitHub repo."""
    import httpx
    headers = {
        "Authorization": f"Bearer {settings.github.token}",
        "Accept": "application/vnd.github+json",
    }
    resp = httpx.get(
        f"https://api.github.com/repos/{repo}/contents/",
        headers=headers,
    )
    if resp.status_code != 200:
        return f"Error: {resp.status_code}"
    items = resp.json()
    lines = [f"{'[dir]' if i['type'] == 'dir' else '     '} {i['name']}" for i in items]
    return f"Repository structure for {repo}:\n" + "\n".join(lines)


@tool
def generate_adr(title: str, context: str, options: list[str]) -> str:
    """Generate an Architecture Decision Record template."""
    options_text = "\n".join(f"  {i+1}. {opt}" for i, opt in enumerate(options))
    return f"""# ADR: {title}

## Status
Proposed

## Context
{context}

## Options Considered
{options_text}

## Decision
[To be filled after evaluation]

## Consequences

### Positive
- [To be determined]

### Negative
- [To be determined]

### Risks
- [To be determined]
"""


@tool
def generate_mermaid_diagram(diagram_type: str, description: str) -> str:
    """Generate a Mermaid diagram template based on description.

    diagram_type: 'flowchart', 'sequence', 'er', 'class', 'c4'
    """
    templates = {
        "flowchart": f"""```mermaid
flowchart TD
    A[Start] --> B{{Decision}}
    B -->|Yes| C[Action 1]
    B -->|No| D[Action 2]
    C --> E[End]
    D --> E
```
Description: {description}""",
        "sequence": f"""```mermaid
sequenceDiagram
    participant User
    participant System
    participant Database
    User->>System: Request
    System->>Database: Query
    Database-->>System: Results
    System-->>User: Response
```
Description: {description}""",
        "er": f"""```mermaid
erDiagram
    ENTITY1 ||--o{{ ENTITY2 : has
    ENTITY1 {{
        string id PK
        string name
    }}
    ENTITY2 {{
        string id PK
        string entity1_id FK
    }}
```
Description: {description}""",
    }
    return templates.get(diagram_type, f"Unsupported diagram type: {diagram_type}. Use: flowchart, sequence, er")


SOLUTIONS_TOOLS = [review_pr_architecture, get_repo_structure, generate_adr, generate_mermaid_diagram]


def run_solutions_agent(state: AgentState) -> dict:
    """Execute the solutions/architecture agent."""
    llm = ChatAnthropic(
        model=settings.llm.reasoning_model,
        api_key=settings.llm.anthropic_api_key,
    )
    llm_with_tools = llm.bind_tools(SOLUTIONS_TOOLS)

    messages = [SystemMessage(content=SOLUTIONS_SYSTEM_PROMPT)] + list(state["messages"])

    # ReAct loop
    max_iterations = 8
    for _ in range(max_iterations):
        response = llm_with_tools.invoke(messages)
        messages.append(response)

        if not response.tool_calls:
            break

        for tc in response.tool_calls:
            tool_fn = next((t for t in SOLUTIONS_TOOLS if t.name == tc["name"]), None)
            if tool_fn:
                result = tool_fn.invoke(tc["args"])
                messages.append(ToolMessage(content=str(result), tool_call_id=tc["id"]))

    content = response.content or ""
    return {
        "messages": [AIMessage(content=content)],
        "agent_outputs": {**state.get("agent_outputs", {}), "solutions": content},
    }
