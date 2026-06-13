"""Cron-triggered tasks for the AI Engineer Agent system.

These are meant to be invoked via system cron (crontab) or launchd on macOS.
Each function is a standalone entry point.

Example crontab:
    */30 * * * * cd /path/to/ai_engineer_agent && python -m schedules.cron_jobs quick_check
    0 8 * * 1-5 cd /path/to/ai_engineer_agent && python -m schedules.cron_jobs morning_briefing
    0 18 * * 1-5 cd /path/to/ai_engineer_agent && python -m schedules.cron_jobs eod_summary
"""

from __future__ import annotations

import sys
from datetime import datetime

from langchain_core.messages import HumanMessage

from src.graph import app


THREAD_CONFIG = {"configurable": {"thread_id": "cron"}}


def quick_check():
    """Run every 30 minutes — check for mentions and urgent messages."""
    msg = HumanMessage(
        content="Quick check: look for any Slack mentions or urgent emails in the last 30 minutes. "
        "Only report if there's something that needs my attention. Be brief."
    )
    result = app.invoke({"messages": [msg]}, config=THREAD_CONFIG)
    output = result["messages"][-1].content
    if output and "no" not in output.lower()[:50]:
        print(f"[{datetime.now().strftime('%H:%M')}] {output}")


def morning_briefing():
    """Run daily at 8 AM — full daily briefing."""
    msg = HumanMessage(
        content="Generate my morning briefing for today. Check all channels: "
        "Slack (mentions + key channels), Outlook (unread emails + today's calendar), "
        "Jira (my tickets, any status changes). "
        "Organize by priority. Include a 'Today's Focus' section with top 3 priorities."
    )
    result = app.invoke({"messages": [msg]}, config=THREAD_CONFIG)
    print(result["messages"][-1].content)


def eod_summary():
    """Run daily at 6 PM — end-of-day wrap-up."""
    msg = HumanMessage(
        content="Generate end-of-day summary. Check what happened today: "
        "new messages, ticket updates, PR activity. "
        "List any unresolved items that need attention tomorrow. Keep it concise."
    )
    result = app.invoke({"messages": [msg]}, config=THREAD_CONFIG)
    print(result["messages"][-1].content)


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python -m schedules.cron_jobs <quick_check|morning_briefing|eod_summary>")
        sys.exit(1)

    job_name = sys.argv[1]
    jobs = {
        "quick_check": quick_check,
        "morning_briefing": morning_briefing,
        "eod_summary": eod_summary,
    }

    if job_name not in jobs:
        print(f"Unknown job: {job_name}. Available: {list(jobs.keys())}")
        sys.exit(1)

    jobs[job_name]()
