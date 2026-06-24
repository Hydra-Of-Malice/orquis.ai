"""
Integrations router — full OAuth 2.0 flows for all providers.
Providers: google_calendar, outlook, jira, linear, slack, notion
"""
import os
import json
import secrets
import urllib.parse
from datetime import datetime, timezone, timedelta

import httpx
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_db, AsyncSessionLocal
from app.auth import get_current_user
from app.models.models import IntegrationToken, User
from app.services.crypto import encrypt, decrypt

router = APIRouter(tags=["Integrations"])

# ── Config ──────────────────────────────────────────────────────────────────────

BASE_URL = os.getenv("OAUTH_REDIRECT_BASE_URL", "http://localhost")

PROVIDERS = {
    "google_calendar": {
        "name": "Google Calendar",
        "category": "calendar",
        "client_id": os.getenv("GOOGLE_CLIENT_ID", ""),
        "client_secret": os.getenv("GOOGLE_CLIENT_SECRET", ""),
        "auth_url": "https://accounts.google.com/o/oauth2/v2/auth",
        "token_url": "https://oauth2.googleapis.com/token",
        "scopes": "https://www.googleapis.com/auth/calendar.readonly https://www.googleapis.com/auth/userinfo.email openid offline",
        "extra_params": {"access_type": "offline", "prompt": "consent"},
    },
    "outlook": {
        "name": "Microsoft Outlook",
        "category": "calendar",
        "client_id": os.getenv("MICROSOFT_CLIENT_ID", ""),
        "client_secret": os.getenv("MICROSOFT_CLIENT_SECRET", ""),
        "auth_url": "https://login.microsoftonline.com/common/oauth2/v2.0/authorize",
        "token_url": "https://login.microsoftonline.com/common/oauth2/v2.0/token",
        "scopes": "Calendars.Read offline_access User.Read",
        "extra_params": {},
    },
    "jira": {
        "name": "Jira",
        "category": "tasks",
        "client_id": os.getenv("JIRA_CLIENT_ID", ""),
        "client_secret": os.getenv("JIRA_CLIENT_SECRET", ""),
        "auth_url": "https://auth.atlassian.com/authorize",
        "token_url": "https://auth.atlassian.com/oauth/token",
        "scopes": "read:jira-work write:jira-work read:jira-user read:me offline_access",
        "extra_params": {"audience": "api.atlassian.com", "prompt": "consent"},
    },
    "linear": {
        "name": "Linear",
        "category": "tasks",
        "client_id": os.getenv("LINEAR_CLIENT_ID", ""),
        "client_secret": os.getenv("LINEAR_CLIENT_SECRET", ""),
        "auth_url": "https://linear.app/oauth/authorize",
        "token_url": "https://api.linear.app/oauth/token",
        "scopes": "read write",
        "extra_params": {"prompt": "consent"},
    },
    "slack": {
        "name": "Slack",
        "category": "communication",
        "client_id": os.getenv("SLACK_CLIENT_ID", ""),
        "client_secret": os.getenv("SLACK_CLIENT_SECRET", ""),
        "auth_url": "https://slack.com/oauth/v2/authorize",
        "token_url": "https://slack.com/api/oauth.v2.access",
        "scopes": "chat:write channels:read channels:join",
        "extra_params": {},
    },
    "notion": {
        "name": "Notion",
        "category": "knowledge",
        "client_id": os.getenv("NOTION_CLIENT_ID", ""),
        "client_secret": os.getenv("NOTION_CLIENT_SECRET", ""),
        "auth_url": "https://api.notion.com/v1/oauth/authorize",
        "token_url": "https://api.notion.com/v1/oauth/token",
        "scopes": "",
        "extra_params": {"owner": "user"},
    },
}

# In-memory state store (provider+state → user_id). For production use Redis.
_oauth_states: dict[str, str] = {}


# ── Helper: close popup and refresh parent ────────────────────────────────────

def _popup_close_html(success: bool, message: str) -> str:
    color = "#10b981" if success else "#ef4444"
    icon = "✅" if success else "❌"
    return f"""<!DOCTYPE html>
<html>
<head>
  <title>OAuth Callback</title>
  <style>
    body {{
      font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
      background: #0f0f13;
      color: white;
      display: flex;
      align-items: center;
      justify-content: center;
      height: 100vh;
      margin: 0;
    }}
    .box {{
      text-align: center;
      padding: 2rem;
      border: 1px solid {color}40;
      border-radius: 12px;
      background: {color}10;
    }}
    .icon {{ font-size: 3rem; margin-bottom: 1rem; }}
    h2 {{ color: {color}; margin: 0 0 0.5rem; }}
    p {{ color: #888; margin: 0; }}
  </style>
</head>
<body>
  <div class="box">
    <div class="icon">{icon}</div>
    <h2>{"Connected!" if success else "Connection Failed"}</h2>
    <p>{message}</p>
  </div>
  <script>
    // Notify parent window and close popup
    if (window.opener) {{
      window.opener.postMessage(
        {{"type": "oauth_callback", "success": {"true" if success else "false"}}},
        "*"
      );
    }}
    setTimeout(() => window.close(), {"1500" if success else "3000"});
  </script>
</body>
</html>"""


# ── Available integrations list ───────────────────────────────────────────────

AVAILABLE_INTEGRATIONS = [
    {"provider": "google_calendar", "name": "Google Calendar", "category": "calendar"},
    {"provider": "outlook", "name": "Microsoft Outlook", "category": "calendar"},
    {"provider": "jira", "name": "Jira", "category": "tasks"},
    {"provider": "linear", "name": "Linear", "category": "tasks"},
    {"provider": "notion", "name": "Notion", "category": "knowledge"},
    {"provider": "slack", "name": "Slack", "category": "communication"},
]


# ── List integrations ─────────────────────────────────────────────────────────

@router.get("/integrations")
async def list_integrations(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    result = await db.execute(
        select(IntegrationToken).where(IntegrationToken.user_id == current_user.id)
    )
    connected = {t.provider: t for t in result.scalars().all()}

    return [
        {
            **integration,
            "connected": integration["provider"] in connected,
            "connected_at": (
                connected[integration["provider"]].connected_at.isoformat()
                if integration["provider"] in connected else None
            ),
            "scope": (
                connected[integration["provider"]].scope
                if integration["provider"] in connected else None
            ),
            "configured": bool(PROVIDERS.get(integration["provider"], {}).get("client_id")),
        }
        for integration in AVAILABLE_INTEGRATIONS
    ]


# ── OAuth start — redirect to provider ───────────────────────────────────────

@router.get("/oauth/{provider}/start")
async def oauth_start(
    provider: str,
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    cfg = PROVIDERS.get(provider)
    if not cfg:
        raise HTTPException(status_code=404, detail=f"Unknown provider: {provider}")
    if not cfg["client_id"]:
        raise HTTPException(
            status_code=400,
            detail=f"{cfg['name']} OAuth not configured. Add {provider.upper()}_CLIENT_ID to .env"
        )

    state = secrets.token_urlsafe(32)
    _oauth_states[f"{provider}:{state}"] = str(current_user.id)

    redirect_uri = f"{BASE_URL}/oauth/callback/{provider}"

    params = {
        "client_id": cfg["client_id"],
        "redirect_uri": redirect_uri,
        "response_type": "code",
        "state": state,
        **cfg.get("extra_params", {}),
    }

    # Scopes
    if cfg["scopes"]:
        params["scope"] = cfg["scopes"]

    # Slack uses user_scope for its own OAuth format
    if provider == "slack":
        params["scope"] = cfg["scopes"]

    auth_url = cfg["auth_url"] + "?" + urllib.parse.urlencode(params)
    return RedirectResponse(url=auth_url)


# ── OAuth callback — exchange code for token ──────────────────────────────────

@router.get("/oauth/callback/{provider}", response_class=HTMLResponse)
async def oauth_callback(
    provider: str,
    code: str = None,
    state: str = None,
    error: str = None,
):
    if error:
        return HTMLResponse(_popup_close_html(False, f"OAuth denied: {error}"))

    if not code or not state:
        return HTMLResponse(_popup_close_html(False, "Missing code or state parameter."))

    cfg = PROVIDERS.get(provider)
    if not cfg:
        return HTMLResponse(_popup_close_html(False, f"Unknown provider: {provider}"))

    # Validate state
    state_key = f"{provider}:{state}"
    user_id = _oauth_states.pop(state_key, None)
    if not user_id:
        return HTMLResponse(_popup_close_html(False, "Invalid or expired state token. Please try again."))

    redirect_uri = f"{BASE_URL}/oauth/callback/{provider}"

    # Exchange code for tokens
    try:
        async with httpx.AsyncClient(timeout=30) as client:
            if provider == "slack":
                # Slack uses a different token exchange format
                r = await client.post(
                    cfg["token_url"],
                    data={
                        "client_id": cfg["client_id"],
                        "client_secret": cfg["client_secret"],
                        "code": code,
                        "redirect_uri": redirect_uri,
                    },
                )
            elif provider == "notion":
                import base64
                credentials = base64.b64encode(
                    f"{cfg['client_id']}:{cfg['client_secret']}".encode()
                ).decode()
                r = await client.post(
                    cfg["token_url"],
                    json={"grant_type": "authorization_code", "code": code, "redirect_uri": redirect_uri},
                    headers={"Authorization": f"Basic {credentials}"},
                )
            else:
                r = await client.post(
                    cfg["token_url"],
                    data={
                        "grant_type": "authorization_code",
                        "code": code,
                        "redirect_uri": redirect_uri,
                        "client_id": cfg["client_id"],
                        "client_secret": cfg["client_secret"],
                    },
                )

        if r.status_code not in (200, 201):
            return HTMLResponse(_popup_close_html(False, f"Token exchange failed ({r.status_code})."))

        token_data = r.json()

        # Slack wraps the token differently
        if provider == "slack":
            if not token_data.get("ok"):
                return HTMLResponse(_popup_close_html(False, token_data.get("error", "Slack error")))
            access_token = token_data.get("access_token") or token_data.get("authed_user", {}).get("access_token", "")
            refresh_token = ""
            expires_in = None
            scope = token_data.get("scope", "")
            # Store extra metadata (team, bot token)
            meta = {
                "team_id": token_data.get("team", {}).get("id"),
                "team_name": token_data.get("team", {}).get("name"),
                "bot_token": token_data.get("access_token"),
                "bot_user_id": token_data.get("bot_user_id"),
            }
        else:
            access_token = token_data.get("access_token", "")
            refresh_token = token_data.get("refresh_token", "")
            expires_in = token_data.get("expires_in")
            scope = token_data.get("scope", cfg["scopes"])
            meta = {}

            # Jira: store cloud_id for API calls
            if provider == "jira":
                try:
                    async with httpx.AsyncClient(timeout=15) as c2:
                        r2 = await c2.get(
                            "https://api.atlassian.com/oauth/token/accessible-resources",
                            headers={"Authorization": f"Bearer {access_token}"},
                        )
                    if r2.status_code == 200 and r2.json():
                        resource = r2.json()[0]
                        meta["cloud_id"] = resource.get("id")
                        meta["site_url"] = resource.get("url")
                        meta["site_name"] = resource.get("name")
                except Exception:
                    pass

        if not access_token:
            return HTMLResponse(_popup_close_html(False, "No access token returned."))

        expires_at = None
        if expires_in:
            expires_at = datetime.now(timezone.utc) + timedelta(seconds=int(expires_in))

        # Encrypt and store
        async with AsyncSessionLocal() as db:
            result = await db.execute(
                select(IntegrationToken).where(
                    IntegrationToken.user_id == user_id,
                    IntegrationToken.provider == provider,
                )
            )
            token_row = result.scalar_one_or_none()

            enc_access = encrypt(access_token)
            enc_refresh = encrypt(refresh_token) if refresh_token else None

            if token_row:
                token_row.access_token_enc = enc_access
                token_row.refresh_token_enc = enc_refresh
                token_row.token_expires_at = expires_at
                token_row.scope = scope
                token_row.metadata_ = meta
                token_row.connected_at = datetime.now(timezone.utc)
            else:
                token_row = IntegrationToken(
                    user_id=user_id,
                    provider=provider,
                    access_token_enc=enc_access,
                    refresh_token_enc=enc_refresh,
                    token_expires_at=expires_at,
                    scope=scope,
                    metadata_=meta,
                )
                db.add(token_row)

            await db.commit()

        return HTMLResponse(_popup_close_html(True, f"{cfg['name']} connected successfully!"))

    except Exception as exc:
        print(f"[oauth_callback] {provider} error: {exc}", flush=True)
        return HTMLResponse(_popup_close_html(False, f"Unexpected error: {str(exc)[:100]}"))


# ── Disconnect ─────────────────────────────────────────────────────────────────

@router.delete("/integrations/{provider}")
async def disconnect_integration(
    provider: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    result = await db.execute(
        select(IntegrationToken).where(
            IntegrationToken.user_id == current_user.id,
            IntegrationToken.provider == provider,
        )
    )
    token = result.scalar_one_or_none()
    if token:
        await db.delete(token)
        await db.commit()
    return {"ok": True}


# ── Status check ───────────────────────────────────────────────────────────────

@router.get("/integrations/status")
async def integrations_status(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    result = await db.execute(
        select(IntegrationToken).where(IntegrationToken.user_id == current_user.id)
    )
    tokens = result.scalars().all()
    return {t.provider: True for t in tokens}
