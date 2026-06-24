"""
Bot Manager — manages up to MAX_BOTS concurrent bot slots.
Calls the bot-runner HTTP API to launch bots.
"""
import asyncio
import os
from typing import Optional

import httpx

MAX_BOTS = int(os.getenv("MAX_CONCURRENT_BOTS", "4"))
BOT_RUNNER_URL = os.getenv("BOT_RUNNER_URL", "http://bot-runner:5001")

_slot_map: dict[int, Optional[str]] = {i: None for i in range(MAX_BOTS)}
_lock = asyncio.Lock()


async def allocate_slot(meeting_id: str) -> Optional[int]:
    async with _lock:
        for slot, occupant in _slot_map.items():
            if occupant is None:
                _slot_map[slot] = meeting_id
                return slot
    return None


async def free_slot(meeting_id: str):
    async with _lock:
        for slot, occupant in _slot_map.items():
            if occupant == meeting_id:
                _slot_map[slot] = None
                return


async def spawn_bot_async(
    meeting_id: str,
    meeting_url: str,
    slot: int,
    visual_capture_mode: str = "disabled",
):
    """POST to bot-runner HTTP API to launch a bot."""
    from app.db import AsyncSessionLocal
    from app.models.models import AppSetting
    from sqlalchemy import select

    settings = {}
    try:
        async with AsyncSessionLocal() as session:
            result = await session.execute(select(AppSetting))
            rows = result.scalars().all()
            settings = {s.key: s.value for s in rows}
    except Exception as e:
        import logging
        logging.getLogger("bot_manager").error(f"Failed to fetch DB settings: {e}")

    try:
        async with httpx.AsyncClient(timeout=15) as c:
            await c.post(
                f"{BOT_RUNNER_URL}/join",
                json={
                    "recording_id": meeting_id,  # bot-runner uses recording_id key
                    "meeting_url": meeting_url,
                    "slot": slot,
                    "visual_capture_mode": visual_capture_mode,
                    "settings": settings,
                },
            )
    except Exception as e:
        import logging
        logging.getLogger("bot_manager").error(f"Failed to spawn bot for {meeting_id}: {e}")


def spawn_bot(
    meeting_id: str,
    meeting_url: str,
    slot: int,
    visual_capture_mode: str = "disabled",
):
    """Fire-and-forget bot spawn via async task."""
    import asyncio as _asyncio
    try:
        loop = _asyncio.get_event_loop()
        if loop.is_running():
            loop.create_task(spawn_bot_async(meeting_id, meeting_url, slot, visual_capture_mode))
        else:
            loop.run_until_complete(spawn_bot_async(meeting_id, meeting_url, slot, visual_capture_mode))
    except RuntimeError:
        _asyncio.run(spawn_bot_async(meeting_id, meeting_url, slot, visual_capture_mode))
