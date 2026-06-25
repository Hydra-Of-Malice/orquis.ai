"""
Async LLM client for the FastAPI backend.
Supports Azure OpenAI and OpenAI-compatible endpoints.
DB settings override env vars (5s cache).
"""
import asyncio
import json
import os
import re
import time
from typing import AsyncGenerator

import httpx
from sqlalchemy import text

API_VERSION = "2024-02-01"
_CACHE: dict = {"cfg": None, "ts": 0.0}
_CACHE_TTL_SEC = 5.0


async def _load_from_db() -> dict:
    keys = (
        "llm_provider", "llm_api_style", "llm_endpoint",
        "llm_api_key", "llm_model_main", "llm_model_mini",
    )
    try:
        from app.db import AsyncSessionLocal
        async with AsyncSessionLocal() as s:
            rows = (await s.execute(
                text("SELECT key, value FROM app_settings WHERE key = ANY(:keys)"),
                {"keys": list(keys)},
            )).fetchall()
            return {r[0]: r[1] for r in rows if r[1]}
    except Exception:
        return {}


async def get_config(force_reload: bool = False) -> dict:
    global _CACHE
    now = time.monotonic()
    if not force_reload and _CACHE["cfg"] and (now - _CACHE["ts"]) < _CACHE_TTL_SEC:
        return _CACHE["cfg"]

    db = await _load_from_db()

    def pick(db_key: str, env_key: str, legacy_env: str = "", default: str = "") -> str:
        return (
            db.get(db_key)
            or os.environ.get(env_key, "")
            or (os.environ.get(legacy_env, "") if legacy_env else "")
            or default
        )

    cfg = {
        "provider":   pick("llm_provider",   "LLM_PROVIDER",   default="azure"),
        "api_style":  pick("llm_api_style",  "LLM_API_STYLE",  default="azure"),
        "endpoint":   pick("llm_endpoint",   "LLM_ENDPOINT",   "AZURE_FOUNDRY_ENDPOINT"),
        "api_key":    pick("llm_api_key",    "LLM_API_KEY",    "AZURE_FOUNDRY_KEY"),
        "model_main": pick("llm_model_main", "LLM_MODEL_MAIN", "AZURE_FOUNDRY_GPT4O_DEPLOYMENT", "gpt-4o"),
        "model_mini": pick("llm_model_mini", "LLM_MODEL_MINI", "AZURE_FOUNDRY_GPT4O_MINI_DEPLOYMENT", "gpt-4o-mini"),
    }
    if not cfg["model_mini"]:
        cfg["model_mini"] = cfg["model_main"]

    _CACHE["cfg"] = cfg
    _CACHE["ts"] = now
    return cfg


def invalidate_cache():
    _CACHE["cfg"] = None
    _CACHE["ts"] = 0.0


def _build_url_headers(cfg: dict, model: str) -> tuple[str, dict]:
    style = (cfg.get("api_style") or "azure").lower()
    endpoint = (cfg.get("endpoint") or "").rstrip("/")
    key = cfg.get("api_key") or ""

    if style == "azure":
        url = f"{endpoint}/openai/deployments/{model}/chat/completions?api-version={API_VERSION}"
        headers = {"Content-Type": "application/json"}
        if key:
            headers["api-key"] = key
        return url, headers

    url = f"{endpoint}/chat/completions"
    headers = {"Content-Type": "application/json"}
    if key:
        headers["Authorization"] = f"Bearer {key}"
    return url, headers


async def chat_stream_async(
    messages: list,
    kind: str = "main",
    temperature: float = 0.3,
    max_tokens: int = 2000,
) -> AsyncGenerator[str, None]:
    """Async streaming chat completion — yields text chunks."""
    cfg = await get_config()
    model = cfg["model_main"] if kind == "main" else cfg["model_mini"]
    url, headers = _build_url_headers(cfg, model)

    body: dict = {
        "messages": messages,
        "temperature": temperature,
        "max_tokens": max_tokens,
        "stream": True,
    }
    if cfg.get("api_style", "azure").lower() == "openai":
        body["model"] = model

    async with httpx.AsyncClient(timeout=120) as client:
        async with client.stream("POST", url, headers=headers, json=body) as response:
            response.raise_for_status()
            async for line in response.aiter_lines():
                if not line.startswith("data: "):
                    continue
                data_str = line[6:]
                if data_str.strip() == "[DONE]":
                    break
                try:
                    data = json.loads(data_str)
                    delta = data.get("choices", [{}])[0].get("delta", {})
                    content = delta.get("content", "")
                    if content:
                        yield content
                except json.JSONDecodeError:
                    pass


async def test_connection() -> dict:
    """Ping the configured LLM and return latency."""
    cfg = await get_config(force_reload=True)
    if not cfg.get("endpoint"):
        return {"ok": False, "error": "No LLM endpoint configured"}
    t = time.monotonic()
    try:
        url, headers = _build_url_headers(cfg, cfg["model_mini"])
        body = {"messages": [{"role": "user", "content": "ping"}], "max_tokens": 5}
        if cfg.get("api_style", "azure").lower() == "openai":
            body["model"] = cfg["model_mini"]
        async with httpx.AsyncClient(timeout=15) as client:
            r = await client.post(url, headers=headers, json=body)
            r.raise_for_status()
        ms = int((time.monotonic() - t) * 1000)
        return {
            "ok": True,
            "latency_ms": ms,
            "model": cfg["model_mini"],
            "provider": cfg["provider"],
        }
    except Exception as e:
        return {"ok": False, "error": str(e)}
