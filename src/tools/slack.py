"""Slack API tool wrappers for the Communications Agent."""

from __future__ import annotations

from datetime import datetime, timedelta
from slack_sdk import WebClient
from slack_sdk.errors import SlackApiError

from src.config import settings


def get_client() -> WebClient:
    """Bot token client — for channel history, posting messages."""
    return WebClient(token=settings.slack.bot_token)


def get_user_client() -> WebClient:
    """User token client — for search (requires search:read scope)."""
    return WebClient(token=settings.slack.user_token)


def get_unread_messages(channel_ids: list[str] | None = None, hours_back: int = 24) -> list[dict]:
    """Fetch recent messages from specified channels or DMs."""
    client = get_client()
    oldest = (datetime.now() - timedelta(hours=hours_back)).timestamp()
    messages = []

    try:
        if channel_ids is None:
            # Get conversations the bot is in
            result = client.conversations_list(types="im,mpim,public_channel,private_channel")
            channel_ids = [c["id"] for c in result["channels"]]

        for channel_id in channel_ids:
            history = client.conversations_history(
                channel=channel_id, oldest=str(oldest), limit=50
            )
            for msg in history.get("messages", []):
                messages.append({
                    "channel": channel_id,
                    "user": msg.get("user", "unknown"),
                    "text": msg.get("text", ""),
                    "ts": msg.get("ts", ""),
                    "thread_ts": msg.get("thread_ts"),
                })
    except SlackApiError as e:
        return [{"error": str(e)}]

    return messages


def get_mentions(hours_back: int = 24) -> list[dict]:
    """Search for messages that mention the configured user (requires user token)."""
    user_id = settings.slack.user_id

    if not settings.slack.user_token:
        return [{"error": "SLACK_USER_TOKEN not configured. User token with search:read scope is required for mention search."}]

    client = get_user_client()
    oldest = (datetime.now() - timedelta(hours=hours_back)).timestamp()

    try:
        result = client.search_messages(
            query=f"<@{user_id}>",
            sort="timestamp",
            sort_dir="desc",
            count=20,
        )
        matches = result.get("messages", {}).get("matches", [])
        return [
            {
                "channel": m.get("channel", {}).get("id", ""),
                "user": m.get("user", ""),
                "text": m.get("text", ""),
                "ts": m.get("ts", ""),
                "permalink": m.get("permalink", ""),
            }
            for m in matches
            if float(m.get("ts", "0")) >= oldest
        ]
    except SlackApiError as e:
        return [{"error": str(e)}]


def send_slack_message(channel: str, text: str, thread_ts: str | None = None) -> str:
    """Send a message to a Slack channel or thread."""
    client = get_client()
    try:
        kwargs = {"channel": channel, "text": text}
        if thread_ts:
            kwargs["thread_ts"] = thread_ts
        result = client.chat_postMessage(**kwargs)
        return f"Message sent to {channel} (ts: {result['ts']})"
    except SlackApiError as e:
        return f"Error sending message: {e}"


def get_channel_info(channel_id: str) -> dict:
    """Get channel name and metadata."""
    client = get_client()
    try:
        result = client.conversations_info(channel=channel_id)
        ch = result["channel"]
        return {
            "id": ch["id"],
            "name": ch.get("name", "DM"),
            "topic": ch.get("topic", {}).get("value", ""),
            "purpose": ch.get("purpose", {}).get("value", ""),
        }
    except SlackApiError as e:
        return {"error": str(e)}
