"""Snowflake connector and Cortex function wrappers for the Data Agent."""

from __future__ import annotations

from contextlib import contextmanager
from typing import Any

import snowflake.connector

from src.config import settings


@contextmanager
def get_connection():
    """Create a Snowflake connection from settings."""
    conn = snowflake.connector.connect(
        account=settings.snowflake.account,
        user=settings.snowflake.user,
        password=settings.snowflake.password,
        warehouse=settings.snowflake.warehouse,
        database=settings.snowflake.database,
        schema=settings.snowflake.schema,
    )
    try:
        yield conn
    finally:
        conn.close()


def execute_query(sql: str, params: dict | None = None) -> list[dict]:
    """Execute a SQL query and return results as list of dicts."""
    with get_connection() as conn:
        cur = conn.cursor()
        try:
            cur.execute(sql, params)
            columns = [desc[0] for desc in cur.description] if cur.description else []
            rows = cur.fetchall()
            return [dict(zip(columns, row)) for row in rows]
        finally:
            cur.close()


def get_table_columns(table_name: str) -> list[dict]:
    """Get column metadata for a table."""
    sql = f"DESCRIBE TABLE {table_name}"
    return execute_query(sql)


def profile_table(table_name: str) -> dict[str, Any]:
    """Run basic profiling on a table — row count, nulls, distinct values."""
    with get_connection() as conn:
        cur = conn.cursor()
        try:
            # Row count
            cur.execute(f"SELECT COUNT(*) FROM {table_name}")
            row_count = cur.fetchone()[0]

            # Column stats
            cur.execute(f"DESCRIBE TABLE {table_name}")
            columns = cur.fetchall()

            stats = []
            for col in columns[:20]:  # Limit to first 20 columns
                col_name = col[0]
                cur.execute(
                    f"SELECT COUNT(*) as total, "
                    f"COUNT(DISTINCT \"{col_name}\") as distinct_count, "
                    f"SUM(CASE WHEN \"{col_name}\" IS NULL THEN 1 ELSE 0 END) as null_count "
                    f"FROM {table_name}"
                )
                result = cur.fetchone()
                stats.append({
                    "column": col_name,
                    "type": col[1],
                    "total": result[0],
                    "distinct": result[1],
                    "nulls": result[2],
                    "null_pct": round(result[2] / max(result[0], 1) * 100, 1),
                })

            return {"table": table_name, "row_count": row_count, "columns": stats}
        finally:
            cur.close()


def cortex_complete(prompt: str, model: str = "llama3.1-70b") -> str:
    """Call Snowflake Cortex COMPLETE function."""
    sql = "SELECT SNOWFLAKE.CORTEX.COMPLETE(%(model)s, %(prompt)s) AS response"
    results = execute_query(sql, {"model": model, "prompt": prompt})
    if results:
        return results[0].get("RESPONSE", "")
    return ""


def cortex_summarize(text: str) -> str:
    """Call Snowflake Cortex SUMMARIZE function."""
    sql = "SELECT SNOWFLAKE.CORTEX.SUMMARIZE(%(text)s) AS summary"
    results = execute_query(sql, {"text": text})
    if results:
        return results[0].get("SUMMARY", "")
    return ""


def list_tables(database: str | None = None, schema: str | None = None) -> list[dict]:
    """List tables in a database/schema."""
    db = database or settings.snowflake.database
    sch = schema or settings.snowflake.schema
    sql = f"SHOW TABLES IN {db}.{sch}"
    return execute_query(sql)
