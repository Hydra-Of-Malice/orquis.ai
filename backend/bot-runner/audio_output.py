"""
Plays Azure TTS audio into the Teams meeting via PipeWire loopback.
The audio is injected into the virtual mic sink so all meeting participants hear it.
"""
import asyncio
import os

from audio_setup import BotEnvironment
from tts_client import AzureTTSClient


class AudioOutput:
    def __init__(self, env: BotEnvironment):
        self.env = env
        self._tts = AzureTTSClient()
        self._lock = asyncio.Lock()

    async def speak(self, text: str):
        """Synthesize text via Azure TTS and inject into the meeting mic."""
        async with self._lock:
            audio_bytes = await self._tts.synthesize(text)
            await self._play_wav(audio_bytes)

    async def _play_wav(self, wav_bytes: bytes):
        pulse_env = os.environ.copy()
        pulse_env["PULSE_SERVER"] = f"unix:{self.env.pulse_socket}"

        proc = await asyncio.create_subprocess_exec(
            "ffplay",
            "-nodisp",
            "-autoexit",
            "-f", "wav",
            "-",
            env=pulse_env,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.DEVNULL,
        )
        await proc.communicate(input=wav_bytes)
