"""
FFmpeg audio capture: records PipeWire/PulseAudio virtual sink to WAV file.
"""
import asyncio
import os
import subprocess
from pathlib import Path

from audio_setup import BotEnvironment

STORAGE_PATH = os.getenv("STORAGE_PATH", "/data/recordings")


class AudioCapture:
    def __init__(self, recording_id: str, env: BotEnvironment):
        self.recording_id = recording_id
        self.env = env
        self.wav_path = str(Path(STORAGE_PATH) / f"{recording_id}.wav")
        self._proc: subprocess.Popen | None = None
        self._queue: asyncio.Queue | None = None

    async def start(self):
        import sys, time
        os.makedirs(Path(STORAGE_PATH) / self.recording_id, exist_ok=True)
        self.wav_path = str(Path(STORAGE_PATH) / self.recording_id / "audio.wav")

        pulse_env = os.environ.copy()
        pulse_env["PULSE_SERVER"] = f"unix:{self.env.pulse_socket}"

        # Verify PulseAudio socket is ready (retry up to 10s)
        for attempt in range(10):
            if os.path.exists(self.env.pulse_socket):
                break
            print(f"[audio] Waiting for PulseAudio socket {self.env.pulse_socket} (attempt {attempt+1})", file=sys.stderr)
            time.sleep(1)
        else:
            print(f"[audio] WARNING: PulseAudio socket not found at {self.env.pulse_socket}", file=sys.stderr)

        # List available PulseAudio sinks for debug
        try:
            result = subprocess.run(
                ["pactl", "list", "short", "sources"],
                env=pulse_env, capture_output=True, text=True, timeout=5
            )
            print(f"[audio] PulseAudio sources: {result.stdout.strip()}", file=sys.stderr)
        except Exception as e:
            print(f"[audio] pactl failed: {e}", file=sys.stderr)

        log_path = str(Path(STORAGE_PATH) / self.recording_id / "ffmpeg.log")
        print(f"[audio] Starting ffmpeg → {self.wav_path} (log: {log_path})", file=sys.stderr)

        self._proc = subprocess.Popen(
            [
                "ffmpeg",
                "-y",
                "-f", "pulse",
                "-i", f"{self.env.sink_name}.monitor",
                "-ar", "16000",
                "-ac", "1",
                "-c:a", "pcm_s16le",
                self.wav_path,
            ],
            env=pulse_env,
            stdout=subprocess.DEVNULL,
            stderr=open(log_path, "w"),
        )
        # Give ffmpeg a moment then check it didn't immediately die
        time.sleep(2)
        if self._proc.poll() is not None:
            log_content = open(log_path).read()[-1000:]
            print(f"[audio] ffmpeg died immediately! Exit={self._proc.returncode}\n{log_content}", file=sys.stderr)

        # After 15s, check if any clients are actually sending audio to our sink
        async def _check_sink_inputs():
            await asyncio.sleep(15)
            try:
                r = subprocess.run(
                    ["pactl", "list", "short", "sink-inputs"],
                    env=pulse_env, capture_output=True, text=True, timeout=5
                )
                print(f"[audio] Sink inputs (should show Chromium):\n{r.stdout.strip() or '(none — Chromium not routing audio to sink!)'}", file=sys.stderr)
                r2 = subprocess.run(
                    ["pactl", "list", "short", "clients"],
                    env=pulse_env, capture_output=True, text=True, timeout=5
                )
                print(f"[audio] PulseAudio clients:\n{r2.stdout.strip()}", file=sys.stderr)
            except Exception as e:
                print(f"[audio] pactl sink-inputs failed: {e}", file=sys.stderr)

        asyncio.create_task(_check_sink_inputs())

    async def stream(self, queue: asyncio.Queue):
        """Stream audio chunks into the queue for wake word detection."""
        import struct
        chunk_size = 512
        pulse_env = os.environ.copy()
        pulse_env["PULSE_SERVER"] = f"unix:{self.env.pulse_socket}"

        proc = await asyncio.create_subprocess_exec(
            "ffmpeg",
            "-f", "pulse",
            "-i", f"{self.env.sink_name}.monitor",
            "-ar", "16000",
            "-ac", "1",
            "-f", "s16le",
            "-",
            env=pulse_env,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.DEVNULL,
        )

        while True:
            data = await proc.stdout.read(chunk_size * 2)
            if not data:
                break
            samples = list(struct.unpack(f"{len(data)//2}h", data))
            try:
                queue.put_nowait(samples)
            except asyncio.QueueFull:
                pass

    async def stop(self) -> str:
        if self._proc:
            self._proc.terminate()
            try:
                self._proc.wait(timeout=10)
            except subprocess.TimeoutExpired:
                self._proc.kill()
        return self.wav_path
