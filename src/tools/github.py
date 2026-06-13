"""GitHub API tool wrappers for the Builder Agent."""

from __future__ import annotations

import httpx

from src.config import settings

GITHUB_API = "https://api.github.com"


def _headers() -> dict:
    return {
        "Authorization": f"Bearer {settings.github.token}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }


def list_repos(org: str | None = None, per_page: int = 30) -> list[dict]:
    """List repos for the authenticated user or an organization."""
    endpoint = f"/orgs/{org}/repos" if org else "/user/repos"
    resp = httpx.get(
        f"{GITHUB_API}{endpoint}",
        headers=_headers(),
        params={"per_page": per_page, "sort": "updated"},
    )
    resp.raise_for_status()
    return [
        {"name": r["full_name"], "url": r["html_url"], "default_branch": r["default_branch"]}
        for r in resp.json()
    ]


def get_open_prs(repo: str) -> list[dict]:
    """Get open PRs for a repo (owner/name format)."""
    resp = httpx.get(
        f"{GITHUB_API}/repos/{repo}/pulls",
        headers=_headers(),
        params={"state": "open", "per_page": 20},
    )
    resp.raise_for_status()
    return [
        {
            "number": pr["number"],
            "title": pr["title"],
            "author": pr["user"]["login"],
            "url": pr["html_url"],
            "created_at": pr["created_at"],
            "draft": pr["draft"],
        }
        for pr in resp.json()
    ]


def get_pr_diff(repo: str, pr_number: int) -> str:
    """Get the diff for a specific PR."""
    headers = _headers()
    headers["Accept"] = "application/vnd.github.diff"
    resp = httpx.get(f"{GITHUB_API}/repos/{repo}/pulls/{pr_number}", headers=headers)
    resp.raise_for_status()
    return resp.text[:10000]  # Truncate large diffs


def create_pr(
    repo: str,
    title: str,
    body: str,
    head: str,
    base: str = "main",
    draft: bool = True,
) -> str:
    """Create a pull request."""
    resp = httpx.post(
        f"{GITHUB_API}/repos/{repo}/pulls",
        headers=_headers(),
        json={"title": title, "body": body, "head": head, "base": base, "draft": draft},
    )
    if resp.status_code == 201:
        data = resp.json()
        return f"PR created: {data['html_url']}"
    return f"Error creating PR: {resp.status_code} {resp.text}"


def get_issues(repo: str, labels: str | None = None, state: str = "open") -> list[dict]:
    """Get issues for a repo, optionally filtered by labels."""
    params = {"state": state, "per_page": 20}
    if labels:
        params["labels"] = labels
    resp = httpx.get(f"{GITHUB_API}/repos/{repo}/issues", headers=_headers(), params=params)
    resp.raise_for_status()
    return [
        {
            "number": i["number"],
            "title": i["title"],
            "labels": [l["name"] for l in i["labels"]],
            "assignees": [a["login"] for a in i["assignees"]],
            "url": i["html_url"],
        }
        for i in resp.json()
        if "pull_request" not in i  # Exclude PRs from issues list
    ]


def create_issue(repo: str, title: str, body: str, labels: list[str] | None = None) -> str:
    """Create a GitHub issue."""
    payload = {"title": title, "body": body}
    if labels:
        payload["labels"] = labels
    resp = httpx.post(f"{GITHUB_API}/repos/{repo}/issues", headers=_headers(), json=payload)
    if resp.status_code == 201:
        data = resp.json()
        return f"Issue created: {data['html_url']}"
    return f"Error creating issue: {resp.status_code} {resp.text}"
