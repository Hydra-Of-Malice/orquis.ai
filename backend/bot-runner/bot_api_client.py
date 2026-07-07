"""
HTTP client: bot reports status, queries context, and posts completion
data to the Zapper PM FastAPI backend.

API-path mapping from old Zapper (/api/recordings/...) to new PM backend
(/api/v1/meetings/... and /api/v1/bot/...).
"""
import os
import httpx

BACKEND_URL = os.getenv("BACKEND_URL", "http://backend:8000")


class BotAPIClient:
    def __init__(self, recording_id: str):
        self.recording_id = recording_id
        self._base = f"{BACKEND_URL}/api/v1"

    async def update_status(self, status: str):
        try:
            async with httpx.AsyncClient(timeout=10) as c:
                await c.patch(
                    f"{self._base}/bot/meetings/{self.recording_id}/status",
                    json={"status": status},
                )
        except Exception as exc:
            print(f"[bot_api] update_status({status}) failed: {exc}", flush=True)

    async def update_participants(self, participant_names: list[str]):
        try:
            async with httpx.AsyncClient(timeout=5) as c:
                r = await c.patch(
                    f"{self._base}/meetings/{self.recording_id}/participants",
                    json={"participant_names": participant_names},
                )
                if r.status_code != 200:
                    print(f"[bot_api] update_participants failed status={r.status_code}: {r.text}", flush=True)
        except Exception as e:
            print(f"[bot_api] update_participants error: {e}", flush=True)

    async def rename_speaker(self, old_name: str, new_name: str):
        try:
            async with httpx.AsyncClient(timeout=10) as c:
                await c.patch(
                    f"{self._base}/bot/meetings/{self.recording_id}/transcript/speaker",
                    json={"old_name": old_name, "new_name": new_name},
                )
        except Exception:
            pass

    async def upload_complete(
        self,
        wav_path: str,
        participant_names: list[str],
        audio_size_bytes: int = None,
        duration_seconds: int = None,
    ):
        payload = {
            "wav_path": wav_path,
            "participant_names": participant_names,
            "participant_count": len(participant_names),
        }
        if audio_size_bytes is not None:
            payload["audio_size_bytes"] = audio_size_bytes
        if duration_seconds is not None:
            payload["duration_seconds"] = duration_seconds

        try:
            async with httpx.AsyncClient(timeout=30) as c:
                await c.post(
                    f"{self._base}/bot/{self.recording_id}/complete",
                    json=payload,
                )
        except Exception as exc:
            print(f"[bot_api] upload_complete failed: {exc}", flush=True)

    async def is_muted(self) -> bool:
        try:
            async with httpx.AsyncClient(timeout=5) as c:
                r = await c.get(f"{self._base}/bot/meetings/{self.recording_id}")
                return r.json().get("zapper_muted", False)
        except Exception:
            return False

    async def is_cancelled(self) -> bool:
        try:
            async with httpx.AsyncClient(timeout=5) as c:
                r = await c.get(f"{self._base}/bot/meetings/{self.recording_id}")
                status = r.json().get("status")
                return status not in ("joining", "lobby", "recording")
        except Exception:
            return False

    async def get_rules(self) -> list[dict]:
        # Automation rules — not yet fully implemented; return empty list
        return []

    async def get_participants(self) -> list[str]:
        try:
            async with httpx.AsyncClient(timeout=5) as c:
                r = await c.get(f"{self._base}/bot/meetings/{self.recording_id}")
                return r.json().get("participant_names", [])
        except Exception:
            return []

    async def get_meeting_context(self) -> dict:
        try:
            async with httpx.AsyncClient(timeout=10) as c:
                r = await c.get(f"{self._base}/bot/meetings/{self.recording_id}")
                data = r.json()
                return {
                    "meeting_id": data.get("id"),
                    "title": data.get("title"),
                    "participant_names": data.get("participant_names", []),
                }
        except Exception:
            return {}

    async def ask_llm_proactive(self, prompt: str, context: dict = None) -> str:
        # Proactive LLM answers not in scope for PM edition; return empty
        return ""

    async def log_qa(
        self,
        question: str,
        answer: str,
        triggered_by: str,
        rule_id: str = None,
        latency_ms: int = None,
        asked_at_ms: int = None,
    ):
        # Q&A logging not in scope; silently no-op
        pass

    async def video_ready(self, video_path: str):
        try:
            async with httpx.AsyncClient(timeout=10) as c:
                await c.post(
                    f"{self._base}/bot/{self.recording_id}/video-ready",
                    json={"video_path": video_path},
                )
        except Exception as exc:
            print(f"[bot_api] video_ready failed: {exc}", flush=True)

    async def release_slot(self):
        try:
            async with httpx.AsyncClient(timeout=10) as c:
                await c.post(f"{self._base}/bot/meetings/{self.recording_id}/release-slot")
        except Exception:
            pass
