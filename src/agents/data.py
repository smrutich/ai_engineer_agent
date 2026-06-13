"""Data Agent — handles SQL, dbt, Snowflake, and data profiling tasks.

Responsible for:
- Designing and generating dbt models
- Running data profiling and quality checks
- Creating Cortex Analyst semantic models
- Building transformation pipelines
- Exploratory data analysis
"""

from __future__ import annotations

import uuid
from typing import Any

from langchain_core.messages import AIMessage, SystemMessage, ToolMessage
from langchain_core.tools import tool
from langchain_openai import ChatOpenAI

from src.config import settings
from src.state import AgentState, AgentType, PendingAction


DATA_SYSTEM_PROMPT = """You are the Data Agent for an AI Engineer.
Your job is to handle all data engineering tasks: SQL, dbt modeling, profiling, and Snowflake operations.

You can:
1. Query Snowflake tables and views
2. Profile tables (row counts, nulls, distinct values)
3. Generate dbt models (staging, intermediate, marts)
4. Run dbt commands (compile, run, test)
5. List available tables and their schemas
6. Use Snowflake Cortex for AI-powered data tasks

When generating dbt models:
- Follow the staging → intermediate → marts pattern
- Add appropriate tests (not_null, unique, accepted_values)
- Use CTEs for readability
- Include source freshness checks for raw sources

When writing SQL:
- Use explicit column lists (no SELECT *)
- Add comments for complex logic
- Consider performance (partition pruning, clustering keys)

Output file contents with clear markers so they can be written to disk.
"""


@tool
def query_snowflake(sql: str) -> str:
    """Execute a SQL query against Snowflake and return results."""
    from src.tools.snowflake import execute_query
    try:
        results = execute_query(sql)
        if not results:
            return "Query returned no results."
        # Format as readable table
        import json
        return json.dumps(results[:50], indent=2, default=str)
    except Exception as e:
        return f"Query error: {e}"


@tool
def profile_table(table_name: str) -> str:
    """Run profiling on a Snowflake table — row count, nulls, distinct values per column."""
    from src.tools.snowflake import profile_table as _profile
    try:
        import json
        result = _profile(table_name)
        return json.dumps(result, indent=2, default=str)
    except Exception as e:
        return f"Profiling error: {e}"


@tool
def list_snowflake_tables(database: str, schema: str) -> str:
    """List all tables in a Snowflake database.schema."""
    from src.tools.snowflake import list_tables
    try:
        import json
        tables = list_tables(database=database, schema=schema)
        return json.dumps(tables[:50], indent=2, default=str)
    except Exception as e:
        return f"Error listing tables: {e}"


@tool
def get_table_schema(table_name: str) -> str:
    """Get column definitions for a table."""
    from src.tools.snowflake import get_table_columns
    try:
        import json
        cols = get_table_columns(table_name)
        return json.dumps(cols, indent=2, default=str)
    except Exception as e:
        return f"Error getting schema: {e}"


@tool
def run_dbt(command: str, select: str | None = None) -> str:
    """Run a dbt command (run, test, compile, docs generate)."""
    from src.tools.dbt import run_dbt_command
    result = run_dbt_command(command, select=select)
    return f"Exit code: {result['exit_code']}\n{result['stdout'][:2000]}"


@tool
def generate_dbt_model(model_name: str, source_table: str, columns: list[str]) -> str:
    """Generate a dbt model SQL file from a source table and column list."""
    from src.tools.dbt import generate_model_sql
    sql = generate_model_sql(model_name, source_table, columns)
    return f"Generated model SQL:\n```sql\n{sql}\n```"


@tool
def cortex_ai_query(prompt: str) -> str:
    """Use Snowflake Cortex AI to answer a data question."""
    from src.tools.snowflake import cortex_complete
    try:
        return cortex_complete(prompt)
    except Exception as e:
        return f"Cortex error: {e}"


DATA_TOOLS = [
    query_snowflake,
    profile_table,
    list_snowflake_tables,
    get_table_schema,
    run_dbt,
    generate_dbt_model,
    cortex_ai_query,
]


def run_data_agent(state: AgentState) -> dict:
    """Execute the data agent."""
    llm = ChatOpenAI(
        model=settings.llm.sql_model,
        api_key=settings.llm.openai_api_key,
    )
    llm_with_tools = llm.bind_tools(DATA_TOOLS)

    messages = [SystemMessage(content=DATA_SYSTEM_PROMPT)] + list(state["messages"])

    # ReAct loop
    max_iterations = 10
    for _ in range(max_iterations):
        response = llm_with_tools.invoke(messages)
        messages.append(response)

        if not response.tool_calls:
            break

        for tc in response.tool_calls:
            tool_fn = next((t for t in DATA_TOOLS if t.name == tc["name"]), None)
            if tool_fn:
                result = tool_fn.invoke(tc["args"])
                messages.append(ToolMessage(content=str(result), tool_call_id=tc["id"]))

    return {
        "messages": [AIMessage(content=response.content)],
        "agent_outputs": {**state.get("agent_outputs", {}), "data": response.content},
    }
