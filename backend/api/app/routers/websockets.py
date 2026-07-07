"""
WebSocket router — real-time live meeting transcript feed.
Subscribes to Redis PubSub channels published by the bot and worker.
"""
import asyncio
import json
import os
from typing import Dict, Set

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

router = APIRouter(tags=["WebSockets"])

_meeting_connections: Dict[str, Set[WebSocket]] = {}


@router.websocket("/ws/meetings/{meeting_id}")
async def ws_meeting(websocket: WebSocket, meeting_id: str):
    await websocket.accept()
    if meeting_id not in _meeting_connections:
        _meeting_connections[meeting_id] = set()
    _meeting_connections[meeting_id].add(websocket)

    redis_url = os.getenv("REDIS_URL", "redis://redis:6379/0")
    r = None
    try:
        import redis.asyncio as aioredis
        r = aioredis.from_url(redis_url)
        pubsub = r.pubsub()
        await pubsub.subscribe(f"zapper:live:{meeting_id}")

        async def redis_listener():
            try:
                async for message in pubsub.listen():
                    if message["type"] == "message":
                        try:
                            data = json.loads(message["data"])
                            await websocket.send_json(data)
                        except Exception as e:
                            print(f"[websocket] Error sending json: {e}", flush=True)
            except Exception as e:
                print(f"[websocket] Redis listener error: {e}", flush=True)
                raise e

        results = await asyncio.gather(
            redis_listener(),
            _ws_keepalive(websocket),
            return_exceptions=True,
        )
        print(f"[websocket] Gather finished for meeting {meeting_id}: {results}", flush=True)
    except WebSocketDisconnect:
        pass
    except Exception as e:
        print(f"[websocket] Error for meeting {meeting_id}: {e}", flush=True)
    finally:
        _meeting_connections.get(meeting_id, set()).discard(websocket)
        if r:
            try:
                await r.aclose()
            except Exception:
                pass


@router.websocket("/ws/meetings/{meeting_id}/live")
async def ws_meeting_live_alias(websocket: WebSocket, meeting_id: str):
    """Alias kept for bot-runner compatibility."""
    await ws_meeting(websocket, meeting_id)


async def _ws_keepalive(ws: WebSocket):
    while True:
        await asyncio.sleep(30)
        try:
            await ws.send_json({"type": "ping"})
        except Exception:
            break
