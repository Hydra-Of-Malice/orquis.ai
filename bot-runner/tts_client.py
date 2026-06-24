"""
Azure Neural TTS REST client — synthesizes text to WAV bytes.
Change voice via AZURE_TTS_VOICE env var — no code change needed.
Voices: en-US-AriaNeural (warm female default), en-US-GuyNeural (male),
        en-GB-SoniaNeural (British female), en-US-JennyNeural
"""
import httpx
import os

SPEECH_KEY = os.environ.get("AZURE_SPEECH_KEY", "")
SPEECH_EP = os.environ.get("AZURE_SPEECH_ENDPOINT", "")
TTS_VOICE = os.getenv("AZURE_TTS_VOICE", "en-US-AriaNeural")


class AzureTTSClient:
    async def synthesize(self, text: str) -> bytes:
        ssml = (
            f"<speak version='1.0' xml:lang='en-US'>"
            f"<voice name='{TTS_VOICE}'>"
            f"<prosody rate='1.05' pitch='+2Hz'>{text}</prosody>"
            f"</voice></speak>"
        )
        async with httpx.AsyncClient(timeout=20) as c:
            r = await c.post(
                f"{SPEECH_EP}/cognitiveservices/v1",
                headers={
                    "Ocp-Apim-Subscription-Key": SPEECH_KEY,
                    "Content-Type": "application/ssml+xml",
                    "X-Microsoft-OutputFormat": "riff-16khz-16bit-mono-pcm",
                },
                content=ssml.encode(),
            )
            r.raise_for_status()
            return r.content
