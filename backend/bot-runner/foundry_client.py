"""
Shared Azure AI Foundry client for bot-runner.
Wraps the OpenAI-compatible Azure endpoint for GPT-4o-mini and Whisper calls.
"""
import os
import httpx

ENDPOINT = os.environ.get("AZURE_FOUNDRY_ENDPOINT", "")
KEY = os.environ.get("AZURE_FOUNDRY_KEY", "")
API_VERSION = "2024-02-01"


async def chat_completion(
    model: str,
    messages: list,
    temperature: float = 0.7,
    max_tokens: int = 500,
) -> str:
    url = f"{ENDPOINT}openai/deployments/{model}/chat/completions?api-version={API_VERSION}"
    async with httpx.AsyncClient(timeout=30) as client:
        r = await client.post(
            url,
            headers={"api-key": KEY, "Content-Type": "application/json"},
            json={
                "messages": messages,
                "temperature": temperature,
                "max_tokens": max_tokens,
            },
        )
        r.raise_for_status()
        data = r.json()
        return data["choices"][0]["message"]["content"]
