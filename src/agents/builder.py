"""Builder Agent — handles code generation, GitHub PRs, and POC scaffolding.

Responsible for:
- Scaffolding POC projects from requirements
- Generating code (Python, SQL, YAML)
- Creating GitHub PRs with proper descriptions
- Writing and running tests
- Building new agentic system components
"""

from __future__ import annotations

import uuid

from langchain_core.messages import AIMessage, SystemMessage, ToolMessage
from langchain_core.tools import tool
from langchain_openai import ChatOpenAI

from src.config import settings
from src.state import AgentState, AgentType, PendingAction


BUILDER_SYSTEM_PROMPT = """You are the Builder Agent for an AI Engineer.
Your job is to write code, scaffold projects, and manage GitHub operations.

You can:
1. List repos and check open PRs
2. View PR diffs for code review
3. Create PRs and issues on GitHub
4. Generate project scaffolds
5. Write Python, SQL, YAML, and config files

When generating code:
- Follow existing patterns in the target repository
- Include type hints and docstrings for public functions
- Write modular, testable code
- Use pyproject.toml for Python projects (not setup.py)

When creating PRs:
- Write clear, descriptive PR titles and bodies
- Reference related issues
- Mark as draft by default (human reviews before merging)

IMPORTANT: PR creation and issue creation are external actions
that must be queued as pending_actions for human approval.
Read operations (listing PRs, viewing diffs) can proceed directly.
"""


@tool
def list_github_repos(org: str | None = None) -> str:
    """List GitHub repositories for the user or an organization."""
    from src.tools.github import list_repos
    import json
    repos = list_repos(org=org)
    return json.dumps(repos, indent=2)


@tool
def get_open_pull_requests(repo: str) -> str:
    """Get open PRs for a repository (format: owner/repo)."""
    from src.tools.github import get_open_prs
    import json
    prs = get_open_prs(repo)
    if not prs:
        return f"No open PRs in {repo}."
    return json.dumps(prs, indent=2)


@tool
def view_pr_diff(repo: str, pr_number: int) -> str:
    """View the diff for a specific pull request."""
    from src.tools.github import get_pr_diff
    diff = get_pr_diff(repo, pr_number)
    return diff if diff else "Could not fetch diff."


@tool
def get_repo_issues(repo: str, labels: str | None = None) -> str:
    """Get open issues for a repo, optionally filtered by labels."""
    from src.tools.github import get_issues
    import json
    issues = get_issues(repo, labels=labels)
    if not issues:
        return f"No open issues in {repo}."
    return json.dumps(issues, indent=2)


@tool
def generate_project_scaffold(
    project_name: str,
    project_type: str,
    description: str,
) -> str:
    """Generate a project scaffold structure.

    project_type: 'python-package', 'fastapi', 'streamlit', 'dbt', 'langgraph-agent'
    """
    scaffolds = {
        "python-package": _python_package_scaffold,
        "fastapi": _fastapi_scaffold,
        "streamlit": _streamlit_scaffold,
        "dbt": _dbt_scaffold,
        "langgraph-agent": _langgraph_scaffold,
    }
    fn = scaffolds.get(project_type, _python_package_scaffold)
    return fn(project_name, description)


def _python_package_scaffold(name: str, desc: str) -> str:
    return f"""Project: {name}
Structure:
  {name}/
  ├── pyproject.toml
  ├── src/{name.replace('-', '_')}/
  │   ├── __init__.py
  │   └── main.py
  ├── tests/
  │   └── test_main.py
  └── README.md

pyproject.toml:
  [project]
  name = "{name}"
  description = "{desc}"
  requires-python = ">=3.11"
"""


def _fastapi_scaffold(name: str, desc: str) -> str:
    return f"""Project: {name} (FastAPI)
Structure:
  {name}/
  ├── pyproject.toml
  ├── src/
  │   ├── __init__.py
  │   ├── main.py          # FastAPI app instance
  │   ├── routes/
  │   │   └── __init__.py
  │   ├── models/
  │   │   └── __init__.py
  │   └── services/
  │       └── __init__.py
  ├── tests/
  │   └── test_routes.py
  └── Dockerfile
"""


def _streamlit_scaffold(name: str, desc: str) -> str:
    return f"""Project: {name} (Streamlit)
Structure:
  {name}/
  ├── pyproject.toml
  ├── app.py               # Main Streamlit app
  ├── pages/
  │   ├── 1_Dashboard.py
  │   └── 2_Settings.py
  ├── components/
  │   └── __init__.py
  └── .streamlit/
      └── config.toml
"""


def _dbt_scaffold(name: str, desc: str) -> str:
    return f"""Project: {name} (dbt)
Structure:
  {name}/
  ├── dbt_project.yml
  ├── profiles.yml
  ├── models/
  │   ├── staging/
  │   │   └── _staging.yml
  │   ├── intermediate/
  │   │   └── _intermediate.yml
  │   └── marts/
  │       └── _marts.yml
  ├── macros/
  ├── seeds/
  └── tests/
"""


def _langgraph_scaffold(name: str, desc: str) -> str:
    return f"""Project: {name} (LangGraph Agent)
Structure:
  {name}/
  ├── pyproject.toml
  ├── src/
  │   ├── __init__.py
  │   ├── graph.py         # Main graph definition
  │   ├── state.py         # State schema
  │   ├── nodes/           # Graph nodes
  │   │   └── __init__.py
  │   └── tools/           # Agent tools
  │       └── __init__.py
  ├── prompts/
  │   └── system.md
  └── tests/
"""


BUILDER_TOOLS = [list_github_repos, get_open_pull_requests, view_pr_diff, get_repo_issues, generate_project_scaffold]


def run_builder_agent(state: AgentState) -> dict:
    """Execute the builder agent."""
    llm = ChatOpenAI(
        model=settings.llm.code_model,
        api_key=settings.llm.openai_api_key,
    )
    llm_with_tools = llm.bind_tools(BUILDER_TOOLS)

    messages = [SystemMessage(content=BUILDER_SYSTEM_PROMPT)] + list(state["messages"])

    # ReAct loop
    max_iterations = 10
    for _ in range(max_iterations):
        response = llm_with_tools.invoke(messages)
        messages.append(response)

        if not response.tool_calls:
            break

        for tc in response.tool_calls:
            tool_fn = next((t for t in BUILDER_TOOLS if t.name == tc["name"]), None)
            if tool_fn:
                result = tool_fn.invoke(tc["args"])
                messages.append(ToolMessage(content=str(result), tool_call_id=tc["id"]))

    # Check for actions requiring approval
    pending_actions = []
    content = response.content or ""
    if "[CREATE PR]" in content or "[CREATE ISSUE]" in content:
        pending_actions.append(
            PendingAction(
                id=str(uuid.uuid4()),
                agent=AgentType.BUILDER,
                description="GitHub action detected — needs review",
                action_type="github_pr",
                payload={"content": content},
            )
        )

    return {
        "messages": [AIMessage(content=content)],
        "pending_actions": state.get("pending_actions", []) + pending_actions,
        "agent_outputs": {**state.get("agent_outputs", {}), "builder": content},
    }
