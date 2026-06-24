"""
Synchronous LLM client for Celery worker tasks.
Mirrors the logic from the backend async client but uses httpx sync.
"""
import json
import os
import re
import time

import httpx
from sqlalchemy import text

from db import get_session

API_VERSION = "2024-02-01"
_CACHE: dict = {"cfg": None, "ts": 0.0}
_CACHE_TTL_SEC = 10.0


def _load_from_db() -> dict:
    keys = (
        "llm_provider", "llm_api_style", "llm_endpoint",
        "llm_api_key", "llm_model_main", "llm_model_mini",
    )
    try:
        with get_session() as session:
            rows = session.execute(
                text("SELECT key, value FROM app_settings WHERE key = ANY(:keys)"),
                {"keys": list(keys)},
            ).fetchall()
            return {r[0]: r[1] for r in rows if r[1]}
    except Exception:
        return {}


def get_config(force_reload: bool = False) -> dict:
    global _CACHE
    now = time.monotonic()
    if not force_reload and _CACHE["cfg"] and (now - _CACHE["ts"]) < _CACHE_TTL_SEC:
        return _CACHE["cfg"]

    db = _load_from_db()

    def pick(db_key, env_key, legacy_env="", default=""):
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


def chat_completion(
    messages: list,
    kind: str = "main",
    temperature: float = 0.3,
    max_tokens: int = 4000,
) -> str:
    cfg = get_config()
    model = cfg["model_main"] if kind == "main" else cfg["model_mini"]
    url, headers = _build_url_headers(cfg, model)
    body: dict = {"messages": messages, "temperature": temperature, "max_tokens": max_tokens}
    if cfg.get("api_style", "azure").lower() == "openai":
        body["model"] = model

    with httpx.Client(timeout=120) as client:
        r = client.post(url, headers=headers, json=body)
        r.raise_for_status()
        return r.json()["choices"][0]["message"]["content"]


def chat_completion_json(
    messages: list,
    kind: str = "main",
    temperature: float = 0.3,
    max_tokens: int = 4000,
) -> dict:
    cfg = get_config()
    model = cfg["model_main"] if kind == "main" else cfg["model_mini"]
    url, headers = _build_url_headers(cfg, model)
    body: dict = {
        "messages": messages,
        "temperature": temperature,
        "max_tokens": max_tokens,
        "response_format": {"type": "json_object"},
    }
    if cfg.get("api_style", "azure").lower() == "openai":
        body["model"] = model

    with httpx.Client(timeout=120) as client:
        r = client.post(url, headers=headers, json=body)
        r.raise_for_status()
        raw = r.json()["choices"][0]["message"]["content"]
        return json.loads(raw)
