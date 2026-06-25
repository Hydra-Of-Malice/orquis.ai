"""
Automations router — CRUD for workflow rules + execution engine.
Triggers: meeting.ended | action_item.created | decision.detected
Actions: create_jira_ticket | create_linear_issue | send_slack_message | send_email
"""
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_db, AsyncSessionLocal
from app.auth import get_current_user
from app.models.models import IntegrationToken, User

router = APIRouter(tags=["Automations"])

# ── Schemas ────────────────────────────────────────────────────────────────────

class AutomationAction(BaseModel):
    type: str  # create_jira_ticket | create_linear_issue | send_slack_message | send_email
    config: Optional[dict] = {}


class CreateAutomationRequest(BaseModel):
    name: str
    trigger: str  # meeting.ended | action_item.created | decision.detected
    conditions: Optional[dict] = {}
    actions: list[AutomationAction]
    is_active: Optional[bool] = True


class UpdateAutomationRequest(BaseModel):
    name: Optional[str] = None
    trigger: Optional[str] = None
    conditions: Optional[dict] = None
    actions: Optional[list[AutomationAction]] = None
    is_active: Optional[bool] = None


# ── CRUD ───────────────────────────────────────────────────────────────────────

@router.get("/automations")
async def list_automations(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    result = await db.execute(
        text("SELECT * FROM automation_rules WHERE org_id = :org_id ORDER BY created_at DESC"),
        {"org_id": str(current_user.org_id)},
    )
    rows = result.mappings().all()
    return [dict(r) for r in rows]


@router.post("/automations", status_code=201)
async def create_automation(
    req: CreateAutomationRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    import json, uuid
    new_id = str(uuid.uuid4())
    actions_json = json.dumps([a.model_dump() for a in req.actions])
    conditions_json = json.dumps(req.conditions or {})

    await db.execute(
        text("""
            INSERT INTO automation_rules
                (id, org_id, created_by, name, trigger, conditions, actions, is_active)
            VALUES
                (:id, :org_id, :created_by, :name, :trigger, :conditions::jsonb, :actions::jsonb, :is_active)
        """),
        {
            "id": new_id,
            "org_id": str(current_user.org_id),
            "created_by": str(current_user.id),
            "name": req.name,
            "trigger": req.trigger,
            "conditions": conditions_json,
            "actions": actions_json,
            "is_active": req.is_active,
        },
    )
    await db.commit()
    return {"id": new_id, "name": req.name, "trigger": req.trigger, "is_active": req.is_active}


@router.patch("/automations/{automation_id}")
async def update_automation(
    automation_id: str,
    req: UpdateAutomationRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    import json
    # Build dynamic SET clause
    updates = {}
    if req.name is not None:
        updates["name"] = req.name
    if req.trigger is not None:
        updates["trigger"] = req.trigger
    if req.conditions is not None:
        updates["conditions"] = json.dumps(req.conditions)
    if req.actions is not None:
        updates["actions"] = json.dumps([a.model_dump() for a in req.actions])
    if req.is_active is not None:
        updates["is_active"] = req.is_active

    if not updates:
        raise HTTPException(status_code=400, detail="No fields to update")

    set_clause = ", ".join(f"{k} = :{k}" for k in updates)
    updates["id"] = automation_id
    updates["org_id"] = str(current_user.org_id)

    await db.execute(
        text(f"UPDATE automation_rules SET {set_clause} WHERE id = :id AND org_id = :org_id"),
        updates,
    )
    await db.commit()
    return {"ok": True}


@router.delete("/automations/{automation_id}")
async def delete_automation(
    automation_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    await db.execute(
        text("DELETE FROM automation_rules WHERE id = :id AND org_id = :org_id"),
        {"id": automation_id, "org_id": str(current_user.org_id)},
    )
    await db.commit()
    return {"ok": True}


# ── Execution Engine ───────────────────────────────────────────────────────────

async def execute_automations(
    trigger: str,
    org_id: str,
    context: dict,
) -> list[dict]:
    """
    Called by pipeline/action_items after events.
    context contains relevant data for the trigger:
      - meeting.ended: {meeting_id, meeting_title, summary_md, action_items: [...]}
      - action_item.created: {action_item: {...}, meeting_title: str}
      - decision.detected: {decision: {...}, meeting_title: str}
    Returns list of execution results.
    """
    results = []

    async with AsyncSessionLocal() as db:
        # Fetch enabled automations for this trigger
        rows = await db.execute(
            text("""
                SELECT * FROM automation_rules
                WHERE org_id = :org_id
                  AND trigger = :trigger
                  AND is_active = true
            """),
            {"org_id": org_id, "trigger": trigger},
        )
        automations = rows.mappings().all()

        if not automations:
            return []

        # Fetch all connected integration tokens for this org
        tokens_result = await db.execute(
            select(IntegrationToken).where(
                IntegrationToken.org_id == org_id
            )
        )
        tokens_by_provider = {t.provider: t for t in tokens_result.scalars().all()}

        import json
        for auto in automations:
            auto_id = auto["id"]
            auto_name = auto["name"]
            actions = auto["actions"] if isinstance(auto["actions"], list) else json.loads(auto["actions"] or "[]")
            conditions = auto["conditions"] if isinstance(auto["conditions"], dict) else json.loads(auto["conditions"] or "{}")

            # Evaluate conditions
            if conditions:
                if "min_duration_seconds" in conditions:
                    duration = context.get("duration_seconds", 0)
                    if duration < conditions["min_duration_seconds"]:
                        print(f"[automations] {auto_name}: skipped (duration {duration}s < {conditions['min_duration_seconds']}s)", flush=True)
                        continue

            # Execute each action
            for action in actions:
                action_type = action.get("type", "")
                action_config = action.get("config", {})
                result_entry = {"automation": auto_name, "action": action_type, "status": "ok", "detail": ""}

                try:
                    if action_type == "create_jira_ticket":
                        token = tokens_by_provider.get("jira")
                        if not token:
                            result_entry["status"] = "skipped"
                            result_entry["detail"] = "Jira not connected"
                        else:
                            from app.services.oauth_push import push_action_item_to_jira
                            action_items = context.get("action_items", [])
                            for item in action_items:
                                if item.get("jira_id"):
                                    continue  # already pushed
                                issue_key = await push_action_item_to_jira(
                                    token,
                                    title=item.get("title", "Meeting Action Item"),
                                    description=item.get("description", ""),
                                    assignee_name=item.get("assignee_name", ""),
                                    priority=item.get("priority", "medium"),
                                    project_key=action_config.get("project"),
                                )
                                # Store jira_id on the action item
                                if issue_key and item.get("id"):
                                    await db.execute(
                                        text("UPDATE action_items SET jira_id = :jira_id WHERE id = :id"),
                                        {"jira_id": issue_key, "id": item["id"]},
                                    )
                            await db.commit()
                            result_entry["detail"] = f"Pushed {len(action_items)} items to Jira"

                    elif action_type == "create_linear_issue":
                        token = tokens_by_provider.get("linear")
                        if not token:
                            result_entry["status"] = "skipped"
                            result_entry["detail"] = "Linear not connected"
                        else:
                            from app.services.oauth_push import push_action_item_to_linear
                            action_items = context.get("action_items", [])
                            for item in action_items:
                                if item.get("linear_id"):
                                    continue  # already pushed
                                issue_id = await push_action_item_to_linear(
                                    token,
                                    title=item.get("title", "Meeting Action Item"),
                                    description=item.get("description", ""),
                                    priority=item.get("priority", "medium"),
                                    team_id=action_config.get("team_id"),
                                )
                                if issue_id and item.get("id"):
                                    await db.execute(
                                        text("UPDATE action_items SET linear_id = :linear_id WHERE id = :id"),
                                        {"linear_id": issue_id, "id": item["id"]},
                                    )
                            await db.commit()
                            result_entry["detail"] = f"Pushed {len(action_items)} items to Linear"

                    elif action_type == "send_slack_message":
                        import os
                        channel = action_config.get("channel") or os.getenv("SLACK_DEFAULT_CHANNEL", "general")
                        channel = channel.lstrip("#")

                        # Use global bot token if available, else user token
                        bot_token = os.getenv("SLACK_BOT_TOKEN", "")
                        slack_token = tokens_by_provider.get("slack")

                        if not bot_token and not slack_token:
                            result_entry["status"] = "skipped"
                            result_entry["detail"] = "Slack not connected"
                        else:
                            from app.services.oauth_push import post_meeting_summary_to_slack
                            # Create a pseudo token row if using global bot token
                            if bot_token and not slack_token:
                                class _FakeToken:
                                    metadata = {"bot_token": bot_token}
                                    access_token_enc = None
                                slack_token = _FakeToken()

                            await post_meeting_summary_to_slack(
                                slack_token,
                                meeting_title=context.get("meeting_title", "Meeting"),
                                summary_md=context.get("summary_md", ""),
                                action_items=context.get("action_items", []),
                                channel=channel,
                            )
                            result_entry["detail"] = f"Posted to #{channel}"

                    elif action_type == "send_email":
                        # Email stub — log for now, implement SMTP later
                        result_entry["status"] = "skipped"
                        result_entry["detail"] = "Email sending not yet configured (add SMTP settings)"

                    else:
                        result_entry["status"] = "unknown"
                        result_entry["detail"] = f"Unknown action type: {action_type}"

                except Exception as exc:
                    result_entry["status"] = "error"
                    result_entry["detail"] = str(exc)[:200]
                    print(f"[automations] Error in {auto_name} / {action_type}: {exc}", flush=True)

                results.append(result_entry)
                print(f"[automations] {auto_name} / {action_type}: {result_entry['status']} — {result_entry['detail']}", flush=True)

    return results
