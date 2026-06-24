"""
OAuth Push Service — push meeting data to connected integrations.
Called by the post-meeting pipeline and automations.
"""
import os
from typing import Optional

import httpx

from app.services.crypto import decrypt


def _get_access_token(token_row) -> str:
    """Decrypt the access token from a stored IntegrationToken row."""
    if not token_row or not token_row.access_token_enc:
        raise ValueError("No access token stored for this integration")
    return decrypt(token_row.access_token_enc)


# ── Jira ──────────────────────────────────────────────────────────────────────

async def get_jira_projects(token_row) -> list[dict]:
    """Fetch available Jira projects for the user to choose from."""
    access_token = _get_access_token(token_row)
    cloud_id = (token_row.metadata_ or {}).get("cloud_id")
    if not cloud_id:
        raise ValueError("Jira cloud_id not found. Please reconnect Jira.")

    url = f"https://api.atlassian.com/ex/jira/{cloud_id}/rest/api/3/project/search"
    async with httpx.AsyncClient(timeout=20) as client:
        r = await client.get(
            url,
            headers={"Authorization": f"Bearer {access_token}", "Accept": "application/json"},
        )
    r.raise_for_status()
    values = r.json().get("values", [])
    return [{"id": p["id"], "key": p["key"], "name": p["name"]} for p in values]


async def push_action_item_to_jira(
    token_row,
    title: str,
    description: str = "",
    assignee_name: str = "",
    priority: str = "medium",
    project_key: str = None,
) -> str:
    """
    Create a Jira issue from a meeting action item.
    Returns the created issue key (e.g. 'PROJ-42').
    """
    access_token = _get_access_token(token_row)
    cloud_id = (token_row.metadata_ or {}).get("cloud_id")
    if not cloud_id:
        raise ValueError("Jira cloud_id not found. Please reconnect Jira.")

    # Fallback project key from metadata or env
    if not project_key:
        project_key = (token_row.metadata_ or {}).get("default_project_key") or os.getenv("JIRA_DEFAULT_PROJECT_KEY", "")
    if not project_key:
        raise ValueError("No Jira project key set. Configure a default project in Settings.")

    priority_map = {"low": "Low", "medium": "Medium", "high": "High", "urgent": "Highest"}
    jira_priority = priority_map.get(priority, "Medium")

    payload = {
        "fields": {
            "project": {"key": project_key},
            "summary": title[:255],
            "description": {
                "type": "doc",
                "version": 1,
                "content": [{"type": "paragraph", "content": [{"type": "text", "text": description or title}]}],
            },
            "issuetype": {"name": "Task"},
            "priority": {"name": jira_priority},
        }
    }

    url = f"https://api.atlassian.com/ex/jira/{cloud_id}/rest/api/3/issue"
    async with httpx.AsyncClient(timeout=30) as client:
        r = await client.post(
            url,
            json=payload,
            headers={
                "Authorization": f"Bearer {access_token}",
                "Accept": "application/json",
                "Content-Type": "application/json",
            },
        )
    r.raise_for_status()
    data = r.json()
    issue_key = data.get("key", "")
    print(f"[jira] Created issue {issue_key}: {title}", flush=True)
    return issue_key


# ── Linear ───────────────────────────────────────────────────────────────────

async def get_linear_teams(token_row) -> list[dict]:
    """Fetch Linear teams for project selection."""
    access_token = _get_access_token(token_row)
    query = """
    query { teams { nodes { id name key } } }
    """
    async with httpx.AsyncClient(timeout=20) as client:
        r = await client.post(
            "https://api.linear.app/graphql",
            json={"query": query},
            headers={"Authorization": f"Bearer {access_token}", "Content-Type": "application/json"},
        )
    r.raise_for_status()
    teams = r.json().get("data", {}).get("teams", {}).get("nodes", [])
    return [{"id": t["id"], "name": t["name"], "key": t["key"]} for t in teams]


async def push_action_item_to_linear(
    token_row,
    title: str,
    description: str = "",
    priority: str = "medium",
    team_id: str = None,
) -> str:
    """
    Create a Linear issue from a meeting action item.
    Returns the created issue ID.
    """
    access_token = _get_access_token(token_row)

    if not team_id:
        team_id = (token_row.metadata_ or {}).get("default_team_id", "")
    if not team_id:
        # Auto-pick first team
        teams = await get_linear_teams(token_row)
        if not teams:
            raise ValueError("No Linear teams found.")
        team_id = teams[0]["id"]

    priority_map = {"urgent": 1, "high": 2, "medium": 3, "low": 4}
    linear_priority = priority_map.get(priority, 3)

    mutation = """
    mutation CreateIssue($title: String!, $desc: String, $teamId: String!, $priority: Int) {
      issueCreate(input: {
        title: $title,
        description: $desc,
        teamId: $teamId,
        priority: $priority
      }) {
        success
        issue { id identifier url }
      }
    }
    """
    variables = {
        "title": title[:255],
        "desc": description or title,
        "teamId": team_id,
        "priority": linear_priority,
    }

    async with httpx.AsyncClient(timeout=30) as client:
        r = await client.post(
            "https://api.linear.app/graphql",
            json={"query": mutation, "variables": variables},
            headers={"Authorization": f"Bearer {access_token}", "Content-Type": "application/json"},
        )
    r.raise_for_status()
    data = r.json()
    issue = data.get("data", {}).get("issueCreate", {}).get("issue", {})
    issue_id = issue.get("identifier", issue.get("id", ""))
    print(f"[linear] Created issue {issue_id}: {title}", flush=True)
    return issue_id


# ── Slack ────────────────────────────────────────────────────────────────────

async def post_slack_message(
    token_row,
    message: str,
    channel: str = None,
) -> bool:
    """Post a message to a Slack channel."""
    # Use global bot token first (set during workspace install), then per-user OAuth token
    bot_token = (
        os.getenv("SLACK_BOT_TOKEN", "")
        or (token_row.metadata_ or {}).get("bot_token", "")
        or _get_access_token(token_row)
    )
    if not channel:
        channel = os.getenv("SLACK_DEFAULT_CHANNEL", "general")

    async with httpx.AsyncClient(timeout=20) as client:
        r = await client.post(
            "https://slack.com/api/chat.postMessage",
            json={"channel": channel, "text": message, "mrkdwn": True},
            headers={"Authorization": f"Bearer {bot_token}", "Content-Type": "application/json"},
        )
    result = r.json()
    if not result.get("ok"):
        print(f"[slack] Error: {result.get('error')}", flush=True)
        return False
    print(f"[slack] Message posted to #{channel}", flush=True)
    return True


async def post_meeting_summary_to_slack(
    token_row,
    meeting_title: str,
    summary_md: str,
    action_items: list[dict],
    channel: str = None,
) -> bool:
    """Post a rich meeting summary card to Slack."""
    # Use global bot token first, then per-user OAuth token
    bot_token = (
        os.getenv("SLACK_BOT_TOKEN", "")
        or (token_row.metadata_ or {}).get("bot_token", "")
        or _get_access_token(token_row)
    )
    if not channel:
        channel = os.getenv("SLACK_DEFAULT_CHANNEL", "general")

    # Build Slack blocks
    action_list = "\n".join(
        f"• *{item.get('assignee_name', 'Unassigned')}*: {item.get('title', '')}"
        for item in action_items[:10]
    )

    blocks = [
        {
            "type": "header",
            "text": {"type": "plain_text", "text": f"📋 Meeting Complete: {meeting_title}", "emoji": True},
        },
        {"type": "divider"},
        {
            "type": "section",
            "text": {"type": "mrkdwn", "text": f"*Summary*\n{summary_md[:600] if summary_md else '_No summary available_'}"},
        },
    ]

    if action_items:
        blocks.append(
            {
                "type": "section",
                "text": {"type": "mrkdwn", "text": f"*Action Items ({len(action_items)})*\n{action_list}"},
            }
        )

    async with httpx.AsyncClient(timeout=20) as client:
        r = await client.post(
            "https://slack.com/api/chat.postMessage",
            json={"channel": channel, "blocks": blocks, "text": f"Meeting complete: {meeting_title}"},
            headers={"Authorization": f"Bearer {bot_token}", "Content-Type": "application/json"},
        )
    result = r.json()
    if not result.get("ok"):
        print(f"[slack] Error posting summary: {result.get('error')}", flush=True)
        return False
    return True


# ── Google Calendar ───────────────────────────────────────────────────────────

async def sync_google_calendar(token_row, max_events: int = 20) -> list[dict]:
    """
    Fetch upcoming Google Calendar events.
    Returns list of event dicts with title, start_time, meeting_url.
    """
    access_token = _get_access_token(token_row)
    from datetime import datetime, timezone
    now = datetime.now(timezone.utc).isoformat()

    url = "https://www.googleapis.com/calendar/v3/calendars/primary/events"
    params = {
        "timeMin": now,
        "maxResults": max_events,
        "singleEvents": "true",
        "orderBy": "startTime",
        "fields": "items(id,summary,start,end,location,conferenceData,hangoutLink)",
    }

    async with httpx.AsyncClient(timeout=20) as client:
        r = await client.get(
            url,
            params=params,
            headers={"Authorization": f"Bearer {access_token}"},
        )

    if r.status_code == 401:
        # Try to refresh token
        refresh_ok = await _refresh_google_token(token_row)
        if not refresh_ok:
            raise ValueError("Google token expired. Please reconnect Google Calendar.")
        access_token = _get_access_token(token_row)
        async with httpx.AsyncClient(timeout=20) as client:
            r = await client.get(url, params=params, headers={"Authorization": f"Bearer {access_token}"})

    r.raise_for_status()
    items = r.json().get("items", [])

    events = []
    for item in items:
        start = item.get("start", {})
        start_time = start.get("dateTime") or start.get("date")
        end = item.get("end", {})
        end_time = end.get("dateTime") or end.get("date")

        # Extract meeting URL (Google Meet or generic)
        meeting_url = (
            item.get("hangoutLink")
            or (item.get("conferenceData") or {}).get("entryPoints", [{}])[0].get("uri", "")
            or item.get("location", "")
        )

        events.append({
            "provider_event_id": item.get("id"),
            "title": item.get("summary", "Untitled Event"),
            "start_time": start_time,
            "end_time": end_time,
            "meeting_url": meeting_url if "meet.google" in (meeting_url or "") or "zoom" in (meeting_url or "") else "",
            "platform": "meet" if "meet.google" in (meeting_url or "") else ("zoom" if "zoom" in (meeting_url or "") else ""),
        })

    return events


async def _refresh_google_token(token_row) -> bool:
    """Refresh a Google OAuth access token using the stored refresh token."""
    if not token_row.refresh_token_enc:
        return False
    try:
        refresh_token = decrypt(token_row.refresh_token_enc)
        async with httpx.AsyncClient(timeout=20) as client:
            r = await client.post(
                "https://oauth2.googleapis.com/token",
                data={
                    "grant_type": "refresh_token",
                    "refresh_token": refresh_token,
                    "client_id": os.getenv("GOOGLE_CLIENT_ID", ""),
                    "client_secret": os.getenv("GOOGLE_CLIENT_SECRET", ""),
                },
            )
        if r.status_code != 200:
            return False
        data = r.json()
        token_row.access_token_enc = encrypt(data["access_token"])
        return True
    except Exception as e:
        print(f"[google] Token refresh failed: {e}", flush=True)
        return False


# ── Microsoft Outlook / Graph ────────────────────────────────────────────────

async def sync_outlook_calendar(token_row, max_events: int = 20) -> list[dict]:
    """
    Fetch upcoming Outlook calendar events via Microsoft Graph.
    Returns list of event dicts.
    """
    access_token = _get_access_token(token_row)
    from datetime import datetime, timezone
    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    url = "https://graph.microsoft.com/v1.0/me/calendarView"
    params = {
        "startDateTime": now,
        "endDateTime": (datetime.now(timezone.utc).replace(day=28)).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "$top": max_events,
        "$select": "id,subject,start,end,onlineMeeting,location",
        "$orderby": "start/dateTime",
    }

    async with httpx.AsyncClient(timeout=20) as client:
        r = await client.get(
            url,
            params=params,
            headers={"Authorization": f"Bearer {access_token}"},
        )

    if r.status_code == 401:
        refresh_ok = await _refresh_microsoft_token(token_row)
        if not refresh_ok:
            raise ValueError("Microsoft token expired. Please reconnect Outlook.")
        access_token = _get_access_token(token_row)
        async with httpx.AsyncClient(timeout=20) as client:
            r = await client.get(url, params=params, headers={"Authorization": f"Bearer {access_token}"})

    r.raise_for_status()
    items = r.json().get("value", [])

    events = []
    for item in items:
        meeting_url = (item.get("onlineMeeting") or {}).get("joinUrl", "")
        events.append({
            "provider_event_id": item.get("id"),
            "title": item.get("subject", "Untitled Event"),
            "start_time": (item.get("start") or {}).get("dateTime"),
            "end_time": (item.get("end") or {}).get("dateTime"),
            "meeting_url": meeting_url,
            "platform": "teams" if "teams.microsoft" in (meeting_url or "") else "",
        })

    return events


async def _refresh_microsoft_token(token_row) -> bool:
    """Refresh a Microsoft OAuth access token."""
    if not token_row.refresh_token_enc:
        return False
    try:
        refresh_token = decrypt(token_row.refresh_token_enc)
        async with httpx.AsyncClient(timeout=20) as client:
            r = await client.post(
                "https://login.microsoftonline.com/common/oauth2/v2.0/token",
                data={
                    "grant_type": "refresh_token",
                    "refresh_token": refresh_token,
                    "client_id": os.getenv("MICROSOFT_CLIENT_ID", ""),
                    "client_secret": os.getenv("MICROSOFT_CLIENT_SECRET", ""),
                    "scope": "Calendars.Read offline_access User.Read",
                },
            )
        if r.status_code != 200:
            return False
        data = r.json()
        token_row.access_token_enc = encrypt(data["access_token"])
        if data.get("refresh_token"):
            token_row.refresh_token_enc = encrypt(data["refresh_token"])
        return True
    except Exception as e:
        print(f"[microsoft] Token refresh failed: {e}", flush=True)
        return False
