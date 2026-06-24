"""
Settings router — bot config, LLM config (DB-stored key-value settings).
"""
from typing import Optional

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_db
from app.auth import get_current_user
from app.models.models import AppSetting, User

router = APIRouter(tags=["Settings"])

BOT_SETTING_DEFAULTS = {
    "bot_name": "Zapper Recorder",
    "lead_time_minutes": "2",
    "max_bots": "4",
    "auto_join": "true",
    "auto_record": "true",
    "language": "en",
    "lobby_timeout_seconds": "300",
    "min_meeting_seconds": "120",
    "max_alone_seconds": "60",
    "auto_leave_when_alone": "true",
    "live_engine": "whisper",
    "live_llm_correct": "false",
    "transcript_llm_correct": "true",
}

LLM_SETTING_KEYS = (
    "llm_provider", "llm_api_style", "llm_endpoint",
    "llm_api_key", "llm_model_main", "llm_model_mini",
)
SENSITIVE_KEYS = {"llm_api_key"}


class BulkSettings(BaseModel):
    bot_name: Optional[str] = None
    lead_time_minutes: Optional[int] = None
    max_bots: Optional[int] = None
    auto_join: Optional[bool] = None
    auto_record: Optional[bool] = None
    language: Optional[str] = None
    lobby_timeout_seconds: Optional[int] = None
    min_meeting_seconds: Optional[int] = None
    max_alone_seconds: Optional[int] = None
    auto_leave_when_alone: Optional[bool] = None
    live_engine: Optional[str] = None
    live_llm_correct: Optional[bool] = None
    transcript_llm_correct: Optional[bool] = None
    llm_provider: Optional[str] = None
    llm_api_style: Optional[str] = None
    llm_endpoint: Optional[str] = None
    llm_api_key: Optional[str] = None
    llm_model_main: Optional[str] = None
    llm_model_mini: Optional[str] = None


def _mask_secret(value: str) -> str:
    if not value:
        return ""
    if len(value) <= 4:
        return "••••"
    return "••••" + value[-4:]


@router.get("/settings")
async def get_settings(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    result = await db.execute(select(AppSetting))
    rows = {s.key: s.value for s in result.scalars().all()}

    for k, default in BOT_SETTING_DEFAULTS.items():
        rows.setdefault(k, default)

    llm_out = {}
    for k in LLM_SETTING_KEYS:
        v = rows.get(k, "") or ""
        if k in SENSITIVE_KEYS:
            llm_out[k] = _mask_secret(v)
            llm_out[f"{k}_set"] = bool(v)
        else:
            llm_out[k] = v

    return {
        "bot_name": rows.get("bot_name", "Zapper Recorder"),
        "lead_time_minutes": int(rows.get("lead_time_minutes", "2")),
        "max_bots": int(rows.get("max_bots", "4")),
        "auto_join": rows.get("auto_join", "true").lower() == "true",
        "auto_record": rows.get("auto_record", "true").lower() == "true",
        "language": rows.get("language", "en"),
        "lobby_timeout_seconds": int(rows.get("lobby_timeout_seconds", "300")),
        "min_meeting_seconds": int(rows.get("min_meeting_seconds", "120")),
        "max_alone_seconds": int(rows.get("max_alone_seconds", "60")),
        "auto_leave_when_alone": rows.get("auto_leave_when_alone", "true").lower() == "true",
        "live_engine": rows.get("live_engine", "whisper"),
        "live_llm_correct": rows.get("live_llm_correct", "false").lower() == "true",
        "transcript_llm_correct": rows.get("transcript_llm_correct", "true").lower() == "true",
        **llm_out,
    }


@router.post("/settings")
async def save_settings(
    req: BulkSettings,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    updates = req.model_dump(exclude_none=True)

    for sk in SENSITIVE_KEYS:
        if sk in updates:
            v = (updates[sk] or "").strip()
            if not v or v.startswith("••••"):
                updates.pop(sk)

    for k, v in updates.items():
        str_val = str(v).lower() if isinstance(v, bool) else str(v)
        result = await db.execute(select(AppSetting).where(AppSetting.key == k))
        setting = result.scalar_one_or_none()
        if setting:
            setting.value = str_val
        else:
            db.add(AppSetting(key=k, value=str_val))

    await db.commit()
    return {"ok": True, "updated": list(updates.keys())}


@router.get("/llm/test")
async def test_llm(current_user: User = Depends(get_current_user)):
    """Ping the configured LLM provider."""
    from app.services.llm_client import test_connection
    return await test_connection()


@router.get("/health")
async def health():
    return {"status": "ok", "service": "zapper-pm-backend"}
