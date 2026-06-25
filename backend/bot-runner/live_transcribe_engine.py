"""
Shared live transcription engine — mirrors the quality filters from
``worker/tasks/transcribe.py`` (``_foundry_one``) so that live 30-second
windows benefit from the same hallucination filtering as the post-meeting
pipeline.

PUBLIC INTERFACE
────────────────
    await transcribe_audio_chunk(wav_bytes, language, speaker_id)
        → list[dict]  # [{text, offset_ms, duration_ms, confidence}]

FILTERS APPLIED (identical to worker/tasks/transcribe.py)
────────────────────────────────────────────────────────
    1. Combined silence check:
       no_speech_prob > 0.6  AND  avg_logprob < -1.0  → drop
    2. Repetition check:
       compression_ratio > 2.4  → drop
    3. Confidence threshold:
       exp(avg_logprob) < MIN_SEGMENT_CONFIDENCE (0.37)  → drop
    4. Consecutive duplicate text  → drop

BACKEND
───────
Foundry only (LIVE_WHISPER_BACKEND=foundry / auto).
Local faster-whisper does not support verbose_json segment-level data;
local backend support can be added in a future iteration.

DO NOT MODIFY worker/tasks/transcribe.py.
This file exists so the live path does not need to import from the worker.
"""
import asyncio
import math
import os
import sys
import tempfile
import subprocess
from concurrent.futures import ThreadPoolExecutor
from typing import Optional

import httpx

# ── Config (mirrors worker/tasks/transcribe.py constants) ──────────────────
FOUNDRY_ENDPOINT = os.environ.get("AZURE_FOUNDRY_ENDPOINT", "").strip()
FOUNDRY_KEY = os.environ.get("AZURE_FOUNDRY_KEY", "").strip()
FOUNDRY_WHISPER_DEPLOYMENT = os.environ.get(
    "AZURE_FOUNDRY_WHISPER_DEPLOYMENT", "whisper"
).strip()
FOUNDRY_API_VERSION = os.environ.get(
    "AZURE_FOUNDRY_WHISPER_API_VERSION", "2024-06-01"
)

# Drop segments below this confidence — matches worker MIN_SEGMENT_CONFIDENCE.
# exp(-1.0) ≈ 0.37 is the canonical Whisper hallucination threshold.
MIN_SEGMENT_CONFIDENCE = float(os.environ.get("WHISPER_MIN_CONFIDENCE", "0.37"))

# mp3 bitrate for Foundry upload. 64kbps mono ≈ 50 min per 25 MB limit.
FOUNDRY_MP3_BITRATE = os.environ.get("FOUNDRY_MP3_BITRATE", "64k")

# Foundry hard upload limit — leave a safety margin.
FOUNDRY_MAX_UPLOAD_BYTES = 24 * 1024 * 1024

# Single-worker executor: keeps Foundry HTTP calls off the event loop and
# serialises ffmpeg subprocesses so they don't stomp each other.
_EXECUTOR = ThreadPoolExecutor(max_workers=2, thread_name_prefix="live-engine")

# Hinglish initial prompt — mirrors the post-meeting worker prompt.
LIVE_WHISPER_INITIAL_PROMPT = os.environ.get("LIVE_WHISPER_INITIAL_PROMPT", "").strip() or None

_LOG = "[live_transcribe_engine]"


# ── Helpers ─────────────────────────────────────────────────────────────────

def _compress_wav_to_mp3(wav_bytes: bytes) -> str:
    """Write wav_bytes to a temp file, transcode to mono 64kbps mp3,
    return the mp3 path. Caller must delete the file when done."""
    # Write input WAV to a temp file (ffmpeg needs a seekable source).
    fd_in, wav_path = tempfile.mkstemp(suffix=".wav", prefix="zapper_live_")
    fd_out, mp3_path = tempfile.mkstemp(suffix=".mp3", prefix="zapper_live_")
    os.close(fd_in)
    os.close(fd_out)
    try:
        with open(wav_path, "wb") as fh:
            fh.write(wav_bytes)
        cmd = [
            "ffmpeg", "-y", "-i", wav_path,
            "-vn", "-ac", "1", "-ar", "16000",
            "-b:a", FOUNDRY_MP3_BITRATE,
            mp3_path,
        ]
        res = subprocess.run(cmd, capture_output=True, text=True)
        if res.returncode != 0:
            raise RuntimeError(f"ffmpeg compression failed: {res.stderr[-400:]}")
        size = os.path.getsize(mp3_path)
        if size > FOUNDRY_MAX_UPLOAD_BYTES:
            raise RuntimeError(
                f"Compressed chunk still {size / 1024 / 1024:.1f} MB — "
                "exceeds Foundry 25 MB limit. Reduce window size or bitrate."
            )
    finally:
        try:
            os.unlink(wav_path)
        except OSError:
            pass
    return mp3_path


def _call_foundry_sync(
    wav_bytes: bytes,
    language: Optional[str],
    speaker_id: str,
    initial_prompt: Optional[str] = None,
) -> list[dict]:
    """
    Blocking Foundry call + segment filtering.  Runs inside the thread executor
    so the asyncio event loop is not blocked.

    Applies the SAME four filters as worker/tasks/transcribe.py _foundry_one():
      1. Combined silence check  (no_speech_prob + avg_logprob)
      2. Repetition / hallucination  (compression_ratio)
      3. Confidence threshold  (MIN_SEGMENT_CONFIDENCE)
      4. Consecutive duplicate text
    """
    mp3_path = None
    try:
        mp3_path = _compress_wav_to_mp3(wav_bytes)

        url = (
            f"{FOUNDRY_ENDPOINT.rstrip('/')}/openai/deployments/"
            f"{FOUNDRY_WHISPER_DEPLOYMENT}/audio/transcriptions"
            f"?api-version={FOUNDRY_API_VERSION}"
        )
        data: dict = {"response_format": "verbose_json"}
        if language:
            data["language"] = language
        prompt_val = initial_prompt if initial_prompt is not None else LIVE_WHISPER_INITIAL_PROMPT
        if prompt_val:
            data["prompt"] = prompt_val

        with open(mp3_path, "rb") as fh:
            files = {"file": (os.path.basename(mp3_path), fh, "audio/mpeg")}
            with httpx.Client(timeout=120) as client:
                r = client.post(
                    url,
                    headers={"api-key": FOUNDRY_KEY},
                    files=files,
                    data=data,
                )

        if r.status_code == 429:
            # Rate limited — honour the Retry-After header and retry once.
            retry_after = 30
            try:
                retry_after = int(r.headers.get("retry-after", 30))
            except (ValueError, TypeError):
                pass
            retry_after = min(retry_after, 60)  # cap at 60s
            print(
                f"{_LOG} {speaker_id}: rate-limited (429), retrying in {retry_after}s",
                file=sys.stderr,
            )
            import time as _time
            _time.sleep(retry_after)
            # Re-open the mp3 file for the retry request
            with open(mp3_path, "rb") as fh:
                files = {"file": (os.path.basename(mp3_path), fh, "audio/mpeg")}
                with httpx.Client(timeout=120) as client:
                    r = client.post(
                        url,
                        headers={"api-key": FOUNDRY_KEY},
                        files=files,
                        data=data,
                    )

        if r.status_code != 200:
            raise RuntimeError(
                f"Foundry HTTP {r.status_code}: {r.text[:400]}"
            )

        body = r.json()
    finally:
        if mp3_path:
            try:
                os.unlink(mp3_path)
            except OSError:
                pass

    detected_lang = body.get("language") or "?"
    raw_segments = body.get("segments") or []
    print(
        f"{_LOG} {speaker_id}: foundry detected={detected_lang} "
        f"segments={len(raw_segments)}",
        file=sys.stderr,
    )

    out: list[dict] = []
    last_text: Optional[str] = None
    stats = {"silent": 0, "repetitive": 0, "low_conf": 0, "dup": 0}

    for seg in raw_segments:
        text_clean = (seg.get("text") or "").strip()
        if not text_clean:
            continue

        avg_logprob = seg.get("avg_logprob")
        no_speech_prob = float(seg.get("no_speech_prob") or 0.0)
        compression_ratio = float(seg.get("compression_ratio") or 1.0)

        # ── Filter 1: Combined silence check (Whisper paper §4.5) ──────────
        # Only drop when BOTH signals agree — no_speech_prob alone is
        # unreliable for Hindi / code-switched audio.
        if (
            no_speech_prob > 0.6
            and isinstance(avg_logprob, (int, float))
            and avg_logprob < -1.0
        ):
            stats["silent"] += 1
            continue

        # ── Filter 2: Repetition / hallucination loop ───────────────────────
        if compression_ratio > 2.4:
            stats["repetitive"] += 1
            continue

        # ── Filter 3: Confidence threshold ─────────────────────────────────
        confidence = (
            math.exp(avg_logprob)
            if isinstance(avg_logprob, (int, float))
            else None
        )
        if confidence is not None and confidence < MIN_SEGMENT_CONFIDENCE:
            stats["low_conf"] += 1
            continue

        # ── Filter 4: Consecutive duplicate ────────────────────────────────
        if text_clean == last_text:
            stats["dup"] += 1
            continue
        last_text = text_clean

        start = float(seg.get("start", 0.0))
        end = float(seg.get("end", start))
        out.append({
            "speaker_id": speaker_id,
            "text": text_clean,
            "offset_ms": int(start * 1000),
            "duration_ms": int(max(0.0, end - start) * 1000),
            "confidence": confidence,
            "detected_lang": detected_lang,
        })
        print(
            f"{_LOG}   {speaker_id} [{start:.1f}-{end:.1f}s] "
            f"({(confidence or 0) * 100:.0f}%) {text_clean[:80]}",
            file=sys.stderr,
        )

    if any(stats.values()):
        print(
            f"{_LOG}   {speaker_id}: dropped "
            f"{stats['silent']} silent, "
            f"{stats['repetitive']} repetitive, "
            f"{stats['low_conf']} low-confidence, "
            f"{stats['dup']} duplicate",
            file=sys.stderr,
        )

    return out


# ── Public API ───────────────────────────────────────────────────────────────

async def transcribe_audio_chunk(
    wav_bytes: bytes,
    language: Optional[str],
    speaker_id: str = "Speaker",
    initial_prompt: Optional[str] = None,
) -> list[dict]:
    """
    Transcribe one audio chunk (WAV bytes) via Azure Foundry Whisper with the
    same quality filters as the post-meeting pipeline.

    Returns a (possibly empty) list of segment dicts:
        [{speaker_id, text, offset_ms, duration_ms, confidence}]

    An empty list means the chunk contained only silence/noise/hallucinations —
    this is NOT an error.  The live loop should simply continue.

    Raises RuntimeError on hard failures (Foundry unreachable, ffmpeg missing).
    The caller (live_context.py) wraps this in try/except so a single failed
    window never terminates the bot.
    """
    if not FOUNDRY_ENDPOINT or not FOUNDRY_KEY:
        raise RuntimeError(
            "AZURE_FOUNDRY_ENDPOINT and AZURE_FOUNDRY_KEY must be set for "
            "the live transcription engine. Set LIVE_WHISPER_BACKEND=local "
            "to use the local faster-whisper path (no verbose_json filtering)."
        )

    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(
        _EXECUTOR,
        _call_foundry_sync,
        wav_bytes,
        language,
        speaker_id,
        initial_prompt,
    )
