"""
Local faster-whisper backend for LIVE transcription (bot-runner).

Drop-in alternative to ``foundry_transcribe.transcribe_question`` with the
exact same contract:

  * ``transcribe_question(wav_bytes)``                       -> str
  * ``transcribe_question(wav_bytes, language="en")``        -> str
  * ``transcribe_question(wav_bytes, return_language=True)`` -> (text, lang)

It runs an in-process faster-whisper model (large-v3 by default) so the live
path can transcribe on a local GPU instead of the Azure Foundry HTTP API.
It is selected via ``LIVE_WHISPER_BACKEND=local`` in ``live_context.py`` and
is only imported when that backend is active, so Foundry-only hosts never
load faster-whisper.

The model is a lazily-loaded singleton.  faster-whisper inference is a
synchronous, compute-bound call, so both the model load and every
transcription run on a dedicated single-worker thread pool via
``loop.run_in_executor``.  That keeps the asyncio event loop responsive and
serializes GPU access, so overlapping 8s chunks don't collide on the device.
"""
import asyncio
import io
import os
import sys
from concurrent.futures import ThreadPoolExecutor

# Reuse the Whisper-name -> ISO-639-1 map so the language tracker behaves
# identically regardless of which backend produced the detection.
from foundry_transcribe import normalize_lang

LIVE_WHISPER_MODEL = os.getenv("LIVE_WHISPER_MODEL", "large-v3")
# "auto" lets faster-whisper pick cuda when available, else cpu.
LIVE_WHISPER_DEVICE = os.getenv("LIVE_WHISPER_DEVICE", "auto")
# "default" lets CTranslate2 choose a sane compute type for the device
# (float16 on GPU, int8 on CPU).
LIVE_WHISPER_COMPUTE = os.getenv("LIVE_WHISPER_COMPUTE", "default")

_MODEL = None  # lazy-loaded singleton
_EXECUTOR = ThreadPoolExecutor(max_workers=1, thread_name_prefix="live-whisper")


def _load_model():
    """Load the faster-whisper model (blocking — runs inside the executor)."""
    global _MODEL
    if _MODEL is None:
        try:
            from faster_whisper import WhisperModel
        except ImportError as exc:  # pragma: no cover - depends on image build
            raise RuntimeError(
                "LIVE_WHISPER_BACKEND=local requires faster-whisper. It is in "
                "bot-runner/requirements.txt — rebuild the image, or set "
                "LIVE_WHISPER_BACKEND=foundry."
            ) from exc
        print(
            f"[local_whisper] Loading faster-whisper model={LIVE_WHISPER_MODEL} "
            f"device={LIVE_WHISPER_DEVICE} compute={LIVE_WHISPER_COMPUTE}",
            file=sys.stderr,
        )
        _MODEL = WhisperModel(
            LIVE_WHISPER_MODEL,
            device=LIVE_WHISPER_DEVICE,
            compute_type=LIVE_WHISPER_COMPUTE,
        )
        print("[local_whisper] Model loaded", file=sys.stderr)
    return _MODEL


def _transcribe_sync(wav_bytes: bytes, language):
    """Blocking transcription of one WAV chunk. Returns (text, detected_lang).

    Uses the same hallucination guards as the offline worker so silent /
    repetitive chunks don't emit "thank you" loops into the live transcript.
    """
    model = _load_model()
    segments, info = model.transcribe(
        io.BytesIO(wav_bytes),
        language=language,
        vad_filter=True,
        beam_size=5,
        no_speech_threshold=0.6,
        log_prob_threshold=-1.0,
        compression_ratio_threshold=2.4,
        condition_on_previous_text=False,
    )
    text = " ".join(s.text.strip() for s in segments if s.text.strip())
    detected = normalize_lang(getattr(info, "language", None))
    return text.strip(), detected


async def preload():
    """Warm the model in the background so the first live chunk isn't slow."""
    loop = asyncio.get_running_loop()
    try:
        await loop.run_in_executor(_EXECUTOR, _load_model)
    except Exception as exc:
        print(
            "[local_whisper] !!! LOCAL WHISPER BACKEND FAILED TO INITIALIZE !!!\n"
            f"[local_whisper] {exc}\n"
            "[local_whisper] Live transcript will be EMPTY until fixed. Check the "
            "GPU/CUDA libraries and LIVE_WHISPER_* settings, or set "
            "LIVE_WHISPER_BACKEND=foundry.",
            file=sys.stderr,
        )


async def transcribe_question(wav_bytes: bytes, language: str | None = None,
                              return_language: bool = False):
    """Local faster-whisper equivalent of foundry_transcribe.transcribe_question."""
    loop = asyncio.get_running_loop()
    text, detected = await loop.run_in_executor(
        _EXECUTOR, _transcribe_sync, wav_bytes, language
    )
    if return_language:
        return text, detected
    return text
