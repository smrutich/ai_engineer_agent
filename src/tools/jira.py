"""Jira/Linear API tool wrappers for the Communications Agent."""

from __future__ import annotations

import base64
import httpx

from src.config import settings


def _jira_headers() -> dict:
    creds = base64.b64encode(
        f"{settings.jira.email}:{settings.jira.api_token}".encode()
    ).decode()
    return {
        "Authorization": f"Basic {creds}",
        "Content-Type": "application/json",
        "Accept": "application/json",
    }


def get_my_tickets(status: str | None = None) -> list[dict]:
    """Get Jira tickets assigned to the current user."""
    jql = "assignee = currentUser() ORDER BY updated DESC"
    if status:
        jql = f"assignee = currentUser() AND status = '{status}' ORDER BY updated DESC"

    resp = httpx.get(
        f"{settings.jira.base_url}/rest/api/3/search",
        headers=_jira_headers(),
        params={"jql": jql, "maxResults": 20, "fields": "summary,status,priority,updated"},
    )
    resp.raise_for_status()
    issues = resp.json().get("issues", [])
    return [
        {
            "key": i["key"],
            "summary": i["fields"]["summary"],
            "status": i["fields"]["status"]["name"],
            "priority": i["fields"].get("priority", {}).get("name", "None"),
            "updated": i["fields"]["updated"],
            "url": f"{settings.jira.base_url}/browse/{i['key']}",
        }
        for i in issues
    ]


def get_ticket_details(ticket_key: str) -> dict:
    """Get full details for a specific ticket."""
    resp = httpx.get(
        f"{settings.jira.base_url}/rest/api/3/issue/{ticket_key}",
        headers=_jira_headers(),
        params={"fields": "summary,description,status,assignee,priority,comment,subtasks"},
    )
    resp.raise_for_status()
    data = resp.json()
    fields = data["fields"]
    return {
        "key": data["key"],
        "summary": fields["summary"],
        "description": _extract_text(fields.get("description")),
        "status": fields["status"]["name"],
        "assignee": fields.get("assignee", {}).get("displayName", "Unassigned"),
        "priority": fields.get("priority", {}).get("name", "None"),
        "comments": [
            {
                "author": c["author"]["displayName"],
                "body": _extract_text(c["body"]),
                "created": c["created"],
            }
            for c in fields.get("comment", {}).get("comments", [])[-5:]
        ],
        "subtasks": [
            {"key": s["key"], "summary": s["fields"]["summary"], "status": s["fields"]["status"]["name"]}
            for s in fields.get("subtasks", [])
        ],
    }


def update_ticket_status(ticket_key: str, transition_name: str) -> str:
    """Transition a ticket to a new status."""
    # First, get available transitions
    resp = httpx.get(
        f"{settings.jira.base_url}/rest/api/3/issue/{ticket_key}/transitions",
        headers=_jira_headers(),
    )
    resp.raise_for_status()
    transitions = resp.json().get("transitions", [])

    target = next(
        (t for t in transitions if t["name"].lower() == transition_name.lower()), None
    )
    if not target:
        available = [t["name"] for t in transitions]
        return f"Transition '{transition_name}' not found. Available: {available}"

    resp = httpx.post(
        f"{settings.jira.base_url}/rest/api/3/issue/{ticket_key}/transitions",
        headers=_jira_headers(),
        json={"transition": {"id": target["id"]}},
    )
    if resp.status_code == 204:
        return f"{ticket_key} transitioned to '{transition_name}'"
    return f"Error: {resp.status_code} {resp.text}"


def add_comment(ticket_key: str, comment_text: str) -> str:
    """Add a comment to a Jira ticket."""
    body = {
        "body": {
            "type": "doc",
            "version": 1,
            "content": [
                {"type": "paragraph", "content": [{"type": "text", "text": comment_text}]}
            ],
        }
    }
    resp = httpx.post(
        f"{settings.jira.base_url}/rest/api/3/issue/{ticket_key}/comment",
        headers=_jira_headers(),
        json=body,
    )
    if resp.status_code == 201:
        return f"Comment added to {ticket_key}"
    return f"Error: {resp.status_code} {resp.text}"


def _extract_text(adf_node: dict | None) -> str:
    """Extract plain text from Atlassian Document Format."""
    if not adf_node:
        return ""
    if isinstance(adf_node, str):
        return adf_node
    text_parts = []
    for content in adf_node.get("content", []):
        if content.get("type") == "text":
            text_parts.append(content.get("text", ""))
        elif "content" in content:
            text_parts.append(_extract_text(content))
    return " ".join(text_parts)
