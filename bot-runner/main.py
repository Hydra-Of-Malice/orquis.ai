"""
Bot Runner — FastAPI HTTP API for spawning meeting bots.
Listens on port 5001. Called by the backend bot_manager service.
Uses the source bots (meet_bot.MeetBot, teams_bot.TeamsBot) unchanged.
"""
import asyncio
import os
import sys
import threading
import traceback

import uvicorn
from fastapi import FastAPI
from pydantic import BaseModel
from typing import Optional

BACKEND_URL = os.getenv("BACKEND_URL", "http://backend:8000")
BOT_DISPLAY_NAME = os.getenv("BOT_DISPLAY_NAME", "Zapper Recorder")
MAX_BOTS = int(os.getenv("MAX_CONCURRENT_BOTS", "4"))

app = FastAPI(title="Zapper PM Bot Runner", version="1.0.0")

_active: dict[str, int] = {}   # meeting_id → slot
_lock = threading.Lock()


class JoinRequest(BaseModel):
    recording_id: str          # backend calls it recording_id for API compat
    meeting_url: str
    slot: Optional[int] = None
    visual_capture_mode: Optional[str] = "disabled"
    settings: Optional[dict] = None


def _pick_bot(recording_id: str, meeting_url: str, slot: int, settings: dict):
    """Return the appropriate bot instance based on the meeting URL."""
    if "meet.google.com" in meeting_url:
        from meet_bot import MeetBot
        return MeetBot(recording_id=recording_id, meeting_url=meeting_url, slot=slot, settings=settings)
    else:
        from teams_bot import TeamsBot
        return TeamsBot(recording_id=recording_id, meeting_url=meeting_url, slot=slot, settings=settings)


def _run_bot_thread(meeting_id: str, meeting_url: str, slot: int, settings: dict):
    """Run the bot in a dedicated thread with its own asyncio event loop."""
    async def _run():
        bot = _pick_bot(meeting_id, meeting_url, slot, settings)
        crashed = False
        err_msg = ""
        try:
            await bot.run()
        except Exception as exc:
            crashed = True
            err_msg = str(exc)
            print(f"[bot-runner] Bot {meeting_id} (slot {slot}) crashed: {exc}", flush=True)
            traceback.print_exc()
        finally:
            with _lock:
                _active.pop(meeting_id, None)
            if crashed:
                try:
                    import httpx
                    async with httpx.AsyncClient(timeout=5) as c:
                        await c.patch(
                            f"{BACKEND_URL}/api/v1/bot/meetings/{meeting_id}/status",
                            json={"status": "error"},
                        )
                        await c.post(
                            f"{BACKEND_URL}/api/v1/bot/meetings/{meeting_id}/release-slot",
                        )
                except Exception as report_err:
                    print(f"[bot-runner] Failed to report crash: {report_err}", flush=True)

    try:
        asyncio.run(_run())
    except Exception as exc:
        print(f"[bot-runner] Thread error for {meeting_id}: {exc}", flush=True)
    finally:
        with _lock:
            _active.pop(meeting_id, None)
        print(f"[bot-runner] Slot {slot} freed for {meeting_id}", flush=True)


@app.post("/join")
async def join(req: JoinRequest):
    meeting_id = req.recording_id

    with _lock:
        if meeting_id in _active:
            return {"ok": True, "slot": _active[meeting_id], "reused": True}
        if len(_active) >= MAX_BOTS:
            return {"ok": False, "error": "Max bots reached"}

        # Determine slot
        slot = req.slot
        if slot is None:
            used = set(_active.values())
            slot = next((i for i in range(MAX_BOTS) if i not in used), None)
        if slot is None:
            return {"ok": False, "error": "No free slots"}

        _active[meeting_id] = slot

    # Merge visual_capture_mode into settings so the bot can read it via get_setting()
    settings = dict(req.settings or {})
    settings["visual_capture_mode"] = req.visual_capture_mode or "disabled"

    thread = threading.Thread(
        target=_run_bot_thread,
        args=(meeting_id, req.meeting_url, slot, settings),
        daemon=True,
        name=f"bot-{meeting_id[:8]}",
    )
    thread.start()
    print(f"[bot-runner] Bot started for {meeting_id} (slot {slot})", flush=True)
    return {"ok": True, "meeting_id": meeting_id, "slot": slot}


@app.get("/health")
async def health():
    return {"status": "ok", "active_bots": len(_active), "max_bots": MAX_BOTS}


@app.get("/slots")
async def slots():
    return {"active": dict(_active), "max": MAX_BOTS, "available": MAX_BOTS - len(_active)}


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=5001, log_level="info")
