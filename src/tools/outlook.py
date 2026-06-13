"""Microsoft Graph API (Outlook) tool wrappers for the Communications Agent."""

from __future__ import annotations

import httpx

from src.config import settings

GRAPH_BASE = "https://graph.microsoft.com/v1.0"


class OutlookClient:
    """Lightweight Microsoft Graph client for mail and calendar."""

    def __init__(self, access_token: str):
        self.headers = {
            "Authorization": f"Bearer {access_token}",
            "Content-Type": "application/json",
        }

    def _get(self, endpoint: str, params: dict | None = None) -> dict:
        resp = httpx.get(f"{GRAPH_BASE}{endpoint}", headers=self.headers, params=params)
        resp.raise_for_status()
        return resp.json()

    def _post(self, endpoint: str, json_body: dict) -> dict:
        resp = httpx.post(f"{GRAPH_BASE}{endpoint}", headers=self.headers, json=json_body)
        resp.raise_for_status()
        return resp.json()


_client: OutlookClient | None = None


def get_client(access_token: str | None = None) -> OutlookClient:
    """Get or create the Outlook client. Requires an OAuth access token."""
    global _client
    if access_token:
        _client = OutlookClient(access_token)
    if _client is None:
        raise RuntimeError(
            "Outlook client not initialized. Call get_client(access_token) first."
        )
    return _client


def get_recent_emails(top: int = 20, unread_only: bool = True) -> list[dict]:
    """Fetch recent emails from the user's inbox."""
    client = get_client()
    params = {"$top": str(top), "$orderby": "receivedDateTime desc"}
    if unread_only:
        params["$filter"] = "isRead eq false"

    data = client._get("/me/messages", params=params)
    return [
        {
            "id": msg["id"],
            "subject": msg.get("subject", ""),
            "from": msg.get("from", {}).get("emailAddress", {}).get("address", ""),
            "received": msg.get("receivedDateTime", ""),
            "preview": msg.get("bodyPreview", "")[:200],
            "is_read": msg.get("isRead", False),
            "has_attachments": msg.get("hasAttachments", False),
        }
        for msg in data.get("value", [])
    ]


def get_calendar_events(days_ahead: int = 7) -> list[dict]:
    """Fetch upcoming calendar events."""
    from datetime import datetime, timedelta

    client = get_client()
    start = datetime.utcnow().isoformat() + "Z"
    end = (datetime.utcnow() + timedelta(days=days_ahead)).isoformat() + "Z"

    data = client._get(
        "/me/calendarView",
        params={"startDateTime": start, "endDateTime": end, "$top": "50"},
    )
    return [
        {
            "id": ev["id"],
            "subject": ev.get("subject", ""),
            "start": ev.get("start", {}).get("dateTime", ""),
            "end": ev.get("end", {}).get("dateTime", ""),
            "organizer": ev.get("organizer", {}).get("emailAddress", {}).get("address", ""),
            "is_online": ev.get("isOnlineMeeting", False),
            "location": ev.get("location", {}).get("displayName", ""),
        }
        for ev in data.get("value", [])
    ]


def send_email(to: str, subject: str, body: str, content_type: str = "Text") -> str:
    """Send an email via Microsoft Graph."""
    client = get_client()
    payload = {
        "message": {
            "subject": subject,
            "body": {"contentType": content_type, "content": body},
            "toRecipients": [{"emailAddress": {"address": to}}],
        },
        "saveToSentItems": True,
    }
    try:
        client._post("/me/sendMail", payload)
        return f"Email sent to {to}: {subject}"
    except httpx.HTTPStatusError as e:
        return f"Error sending email: {e.response.status_code} {e.response.text}"


def create_draft_email(to: str, subject: str, body: str) -> str:
    """Create a draft email (for human-in-the-loop review)."""
    client = get_client()
    payload = {
        "subject": subject,
        "body": {"contentType": "Text", "content": body},
        "toRecipients": [{"emailAddress": {"address": to}}],
    }
    try:
        result = client._post("/me/messages", payload)
        return f"Draft created: {result.get('id', 'unknown')}"
    except httpx.HTTPStatusError as e:
        return f"Error creating draft: {e.response.status_code}"
