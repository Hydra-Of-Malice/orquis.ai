"""
Rolling transcript buffer — maintains the last N minutes of transcript for Q&A context.
Also implements real-time Whisper transcription during the live meeting.
"""
import asyncio
import hashlib
import io
import json
import os
import struct
import sys
import time
import wave
from collections import deque
from dataclasses import dataclass, field
import httpx
import redis
import uuid

SAMPLE_RATE = 16000

# 30-second processing windows: 30 * 16000 = 480,000 samples.
# Larger windows give Whisper more context, matching post-meeting quality.
# The old 8-second window (128,000 samples) lacked per-segment verbose data.
_WINDOW_SAMPLES = 480_000

# Hash eviction: remove dedup hashes older than this many seconds so the
# set stays bounded across long meetings (90 min+ is ~720 hashes at most).
_DEDUP_TTL_SECONDS = 300  # 5 minutes

# How long (seconds) to auto-detect the meeting language before pinning it.
LIVE_LANG_DETECT_SECONDS = float(os.getenv("LIVE_LANG_DETECT_SECONDS", "30"))
# Hard override - when set, skip auto-detection and pin this ISO code.
LIVE_LANGUAGE = (os.getenv("LIVE_LANGUAGE", "").strip() or None)
# Pin the language early once this many confident (non-empty) chunks agree.
LIVE_LANG_MIN_VOTES = int(os.getenv("LIVE_LANG_MIN_VOTES", "3"))
# Live transcription backend: 'foundry' (Azure HTTP, default) or 'local'
# (in-process faster-whisper on a GPU; see local_whisper.py).
LIVE_WHISPER_BACKEND = os.getenv("LIVE_WHISPER_BACKEND", "foundry").strip().lower()

# Live LLM cleanup: when enabled, each 8s chunk is passed through a fast
# mini-LLM to repair obvious mis-hears before it is shown live.  Off by
# default (adds a per-chunk LLM call + latency); the after-meeting pipeline
# runs a far more thorough correction pass on the saved transcript anyway.
LIVE_LLM_CORRECT = os.getenv("LIVE_LLM_CORRECT", "false").strip().lower() in ("1", "true", "yes", "on")
LIVE_LLM_CORRECT_MODEL = os.environ.get("AZURE_FOUNDRY_GPT4O_MINI_DEPLOYMENT", "gpt-4o-mini")

# Whisper hallucinates boilerplate on silence/noise — drop chunks whose
# entire (normalised) text is one of these phrases.
_HALLUCINATION_PHRASES = {
    "thank you", "thanks for watching", "thank you for watching",
    "please subscribe", "subscribe to my channel", "see you next time",
    "thanks for listening", "you",
    # Whisper initial-prompt echo hallucinations (old long prompt fragments)
    "write hindi in devanagari and keep english and technical terms in latin script",
    "the following is a hindi english hinglish code switched conversation",
    "the following is a hindi-english hinglish code-switched conversation",
    "write hindi in devanagari",
    "technical terms in latin script",
    "hindi english hinglish",
    # Fragments from the previous long initial_prompt that leaked into live transcript
    "names company names transcript summary database server branch staging release",
    "names company names product names acronyms numbers dates and technical terms in latin script",
    "do not translate between hindi and english",
    "preserve the speakers original mixed language wording",
    "common meeting terms may include agenda action item deadline follow up client project",
    "deployment backend frontend api database server dashboard recording transcript summary",
    "zoom teams google meet webex bot whisper llm azure openai production staging bug issue",
    "pr branch commit testing release and demo",
    "and demo",
    "this is a hindi english code switched business meeting conversation in hinglish",
    "transcribe hindi words in devanagari script and keep english words",
    "use natural punctuation",
}

# Build a normalised version of the live initial_prompt at import time so we
# can drop any chunk that is a substring of it (dynamic echo guard).
# We ALSO embed the old long default prompt so that any hallucination of it
# is caught even if the bot was started before the .env was updated.
_OLD_LONG_PROMPT = (
    "this is a hindi english code switched business meeting conversation in hinglish "
    "transcribe hindi words in devanagari script and keep english words names company "
    "names product names acronyms numbers dates and technical terms in latin script "
    "do not translate between hindi and english preserve the speakers original mixed "
    "language wording use natural punctuation common meeting terms may include agenda "
    "action item deadline follow up client project deployment backend frontend api "
    "database server dashboard recording transcript summary zoom teams google meet "
    "webex bot whisper llm azure openai production staging bug issue pr branch commit "
    "testing release and demo"
)
_INITIAL_PROMPT_NORM: str = _OLD_LONG_PROMPT  # always includes old prompt as baseline
try:
    _raw_ip = os.environ.get("LIVE_WHISPER_INITIAL_PROMPT", "").strip()
    if _raw_ip:
        import re as _re
        _cleaned = _re.sub(r"[^\w\s]", " ", _raw_ip.lower())
        _INITIAL_PROMPT_NORM = _OLD_LONG_PROMPT + " " + " ".join(_cleaned.split())
except Exception:
    pass  # non-fatal — guard simply won't fire

# Keywords that almost never appear in real Hinglish speech but are common
# in Whisper's hallucinated transcription instruction templates.
_INSTRUCTION_KEYWORDS = {
    "devanagari",        # nobody says this word in speech
    "latin script",      # nobody says this in speech
    "transliteration",   # instruction meta-word
    "keep english words",
    "keep english",
    "do not translate",
    "technical terms in",
    "script and keep",
}


def _contains_instruction_pattern(norm: str) -> bool:
    """Return True when the normalised text looks like a hallucinated
    transcription-instruction template rather than real speech.

    Checks:
    1. Text contains 'devanagari' (almost impossible in spoken Hinglish).
    2. Text contains multiple instruction-specific keyword fragments.
    """
    if "devanagari" in norm:
        return True
    # Count how many instruction-keyword fragments appear
    hits = sum(1 for kw in _INSTRUCTION_KEYWORDS if kw in norm)
    return hits >= 2


def _normalise_phrase(t: str) -> str:
    cleaned = "".join(c if (c.isalnum() or c.isspace()) else " " for c in (t or "").lower())
    return " ".join(cleaned.split())


def _is_repetition(t: str) -> bool:
    """True when the text is one token (or a 1-2 word phrase) looped — a
    classic Whisper hallucination signal."""
    toks = (t or "").split()
    if len(toks) >= 4 and len(set(toks)) == 1:
        return True
    if len(toks) >= 8 and len(set(toks)) <= 2:
        return True
    return False


def _clean_live_text(text: str, last_text: str):
    """Return the text to post, or None to drop it as garbage."""
    t = (text or "").strip()
    if not t:
        return None
    norm = _normalise_phrase(t)
    if not norm or norm in _HALLUCINATION_PHRASES:
        return None
    # Dynamic guard 1: substring of the initial_prompt (covers both old and new prompt).
    if _INITIAL_PROMPT_NORM and len(norm) >= 12 and norm in _INITIAL_PROMPT_NORM:
        return None
    # Dynamic guard 2: keyword-pattern — catches Whisper instruction-template
    # hallucinations regardless of which exact prompt was used.
    if _contains_instruction_pattern(norm):
        return None
    if _is_repetition(t):
        return None
    if last_text and t == last_text.strip():
        return None
    return t


# Phrases that indicate the LLM is responding conversationally rather than
# correcting a transcription chunk.  When detected, we discard the LLM
# output and return the original raw text instead.
_LLM_META_SIGNALS = (
    "please provide",
    "could you provide",
    "could you please",
    "can you please",
    "i need clarification",
    "i need a specific",
    "i'm sorry",
    "im sorry",
    "sorry, i",
    "do you want",
    "could you confirm",
    "what would you like",
    "please clarify",
    "i cannot",
    "i can't",
    "as an ai",
    "as a language model",
)


async def _llm_clean_live(text: str) -> str:
    """Best-effort mini-LLM cleanup of one live chunk; returns the original
    text on any error or when the LLM returns a meta-response instead of
    a corrected line."""
    try:
        from foundry_client import chat_completion
        out = await chat_completion(
            model=LIVE_LLM_CORRECT_MODEL,
            temperature=0.0,
            max_tokens=300,
            messages=[
                {"role": "system", "content": (
                    "You are a transcription corrector for a Hindi/English "
                    "(Hinglish) meeting. The user message is a raw speech-to-text "
                    "segment that may contain mis-heard words or wrong "
                    "transliteration. Fix ONLY obvious errors: keep English and "
                    "technical terms in Latin script, Hindi words in Devanagari. "
                    "Do NOT translate, add, or remove content. "
                    "If the text looks like a list of keywords or is not real "
                    "speech, return it unchanged. "
                    "Return ONLY the corrected text, nothing else."
                )},
                {"role": "user", "content": text},
            ],
        )
        out = (out or "").strip()

        # Guard: if the LLM responded conversationally rather than correcting,
        # discard its output and fall back to the raw transcription.
        out_lower = out.lower()
        if any(sig in out_lower for sig in _LLM_META_SIGNALS):
            print(
                f"[live_context] LLM returned meta-response (discarding): {out[:80]!r}",
                file=sys.stderr,
            )
            return text  # fall back to raw

        # Guard: LLM output must not be absurdly longer than the input
        # (adding content means it misunderstood the task).
        if out and len(out) <= max(40, len(text) * 2):
            return out
    except Exception as e:
        print(f"[live_context] LLM live cleanup failed (using raw): {e}", file=sys.stderr)
    return text


@dataclass
class TranscriptChunk:
    text: str
    speaker: str
    timestamp: float = field(default_factory=time.time)


def _samples_to_wav(samples: list) -> bytes:
    buf = io.BytesIO()
    with wave.open(buf, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(SAMPLE_RATE)
        wf.writeframes(struct.pack(f"{len(samples)}h", *samples))
    return buf.getvalue()


def get_active_speaker_name(track_activity_map: dict, track_name_map: dict, window_seconds: float = 10.0) -> str:
    """Determine the active speaker based on the track with the most frames in the sliding window.

    Returns a clean participant display name, or 'Speaker' if no name is resolved yet.
    Never returns raw track IDs like 'Speaker t2'.
    """
    import time
    now = time.time()
    cutoff = now - window_seconds

    best_track = None
    max_frames = 0

    # Safely iterate keys to avoid dictionary size mutation exceptions
    keys = list(track_activity_map.keys())
    for track_id in keys:
        timestamps = track_activity_map.get(track_id, [])
        recent = [t for t in timestamps if t >= cutoff]
        try:
            track_activity_map[track_id] = recent
        except Exception:
            pass
        if len(recent) > max_frames:
            max_frames = len(recent)
            best_track = track_id

    if best_track and max_frames > 2:
        name = track_name_map.get(best_track, "")
        # If name is empty or looks like a raw track ID (e.g. 't2'), return generic 'Speaker'
        if name and not _is_raw_track_id(name):
            return name
    return "Speaker"


def _is_raw_track_id(name: str) -> bool:
    """Return True if the name looks like a raw WebRTC/Zapper track ID rather than a person's name.
    Examples that should NOT appear as speaker labels: 't1', 't2', '23001'.
    """
    import re
    return bool(re.fullmatch(r't\d+|\d+', name.strip()))


def _normalize_language(lang: str | None) -> str | None:
    """Convert BCP-47 language tags (e.g. 'en-US', 'hi-IN') to ISO-639-1
    codes ('en', 'hi') that the Whisper API requires. Returns None for
    empty/auto-detect values. Already-short codes are passed through."""
    if not lang:
        return None
    # Strip region subtag: 'en-US' → 'en', 'hi-IN' → 'hi'
    iso = lang.strip().split("-")[0].split("_")[0].lower()
    return iso if iso else None


class LiveTranscriptBuffer:
    def __init__(self, recording_id: str | None = None, max_minutes: int = 30, get_speaker_fn = None, language: str | None = None, master_buf = None, settings: dict | None = None):
        self.recording_id = recording_id
        self.max_minutes = max_minutes
        self.get_speaker_fn = get_speaker_fn
        self.master_buf = master_buf
        self.settings = settings or {}
        self._chunks: deque[TranscriptChunk] = deque()
        self._last_live_text = ""
        self._lock = asyncio.Lock()
        # Meeting-level language tracking. Once a language is pinned we pass
        # it as a hint to every chunk so Whisper stops re-detecting per chunk.
        # Normalize to ISO-639-1 ('en-US' → 'en') — Whisper rejects BCP-47.
        _raw_lang = language if language is not None else (self.settings.get("language") or LIVE_LANGUAGE)
        self._language = _normalize_language(_raw_lang)
        self._lang_locked = self._language is not None
        self._lang_votes: dict[str, int] = {}
        self._lang_detect_until = None
        # Deduplication: map SHA-1(text) → timestamp_published so we never
        # post the same text twice across overlapping 30-second windows.
        # Entries are evicted after _DEDUP_TTL_SECONDS to keep memory bounded.
        self._published_hashes: dict[str, float] = {}

    def get_setting_bool(self, key: str, default: bool) -> bool:
        val = self.settings.get(key)
        if val is None:
            return default
        if isinstance(val, bool):
            return val
        return str(val).lower() in ("true", "1", "yes", "on")

    async def add(self, text: str, speaker: str = "unknown"):
        async with self._lock:
            self._chunks.append(TranscriptChunk(text=text, speaker=speaker))
            self._evict_old()
        if self.master_buf:
            await self.master_buf.add(text, speaker)

    def get_recent(self, minutes: int = 10) -> str:
        cutoff = time.time() - (minutes * 60)
        lines = []
        for chunk in self._chunks:
            if chunk.timestamp >= cutoff:
                lines.append(f"{chunk.speaker}: {chunk.text}")
        return "\n".join(lines)

    def get_last_segment(self) -> TranscriptChunk | None:
        """Return the most recent transcript chunk, or None if buffer is empty."""
        if self._chunks:
            return self._chunks[-1]
        return None

    def _evict_old(self):
        cutoff = time.time() - (self.max_minutes * 60)
        while self._chunks and self._chunks[0].timestamp < cutoff:
            self._chunks.popleft()

    def _record_language_vote(self, lang: str):
        """Tally a detected language during the auto-detect window."""
        self._lang_votes[lang] = self._lang_votes.get(lang, 0) + 1

    def _maybe_finalize_language(self):
        """Decide whether to pin the meeting language yet.

        Pins early once enough confident (non-empty) votes agree, which
        makes detection immune to a silent meeting start. If the wall-clock
        window expires with at least one vote, pin the dominant language.
        If it expires with no votes at all (bot still alone in the call),
        extend the window and keep listening rather than locking to nothing.
        """
        if self._lang_locked:
            return
        total = sum(self._lang_votes.values())
        if total >= LIVE_LANG_MIN_VOTES:
            self._finalize_language()
            return
        window_expired = (
            self._lang_detect_until is not None
            and time.time() > self._lang_detect_until
        )
        if window_expired:
            if self._lang_votes:
                self._finalize_language()
            else:
                import sys
                self._lang_detect_until = time.time() + LIVE_LANG_DETECT_SECONDS
                print(
                    "[live_context] No speech detected yet; extending "
                    "language detection window",
                    file=sys.stderr,
                )

    def _finalize_language(self):
        """Pick the most-voted language, normalize to ISO-639-1, and pin it."""
        if self._lang_locked or not self._lang_votes:
            return
        raw_lang = max(self._lang_votes, key=lambda k: self._lang_votes[k])
        # Whisper returns full English names; Foundry API needs ISO-639-1 codes.
        _LANG_MAP = {
            "english": "en", "hindi": "hi", "french": "fr",
            "spanish": "es", "german": "de", "arabic": "ar",
            "chinese": "zh", "japanese": "ja", "portuguese": "pt",
            "russian": "ru", "italian": "it", "korean": "ko",
            "dutch": "nl", "turkish": "tr", "polish": "pl",
            "urdu": "ur", "bengali": "bn", "punjabi": "pa",
            "marathi": "mr", "gujarati": "gu", "tamil": "ta",
            "telugu": "te", "kannada": "kn", "malayalam": "ml",
            "welsh": "cy", "swedish": "sv", "danish": "da",
            "norwegian": "no", "finnish": "fi", "vietnamese": "vi",
            "thai": "th", "indonesian": "id", "hebrew": "he",
            "greek": "el", "ukrainian": "uk", "romanian": "ro",
            "czech": "cs", "hungarian": "hu", "slovak": "sk",
            "filipino": "tl", "malay": "ms", "swahili": "sw",
        }
        self._language = _LANG_MAP.get((raw_lang or "").lower(), raw_lang)
        self._lang_locked = True
        import sys
        print(
            f"[live_context] Language pinned to {self._language or 'auto'} "
            f"(raw={raw_lang}, votes={self._lang_votes})",
            file=sys.stderr,
        )

    def _segment_hash(self, text: str) -> str:
        """Return a short SHA-1 hex digest for deduplication keying."""
        return hashlib.sha1(text.lower().strip().encode()).hexdigest()

    def _evict_old_hashes(self) -> None:
        """Remove dedup entries older than _DEDUP_TTL_SECONDS."""
        cutoff = time.time() - _DEDUP_TTL_SECONDS
        stale = [h for h, ts in self._published_hashes.items() if ts < cutoff]
        for h in stale:
            del self._published_hashes[h]

    def _is_duplicate(self, text: str) -> bool:
        """True if this text was published within the dedup TTL window."""
        return self._segment_hash(text) in self._published_hashes

    def _mark_published(self, text: str) -> None:
        """Record this text as published for future dedup checks."""
        self._evict_old_hashes()
        self._published_hashes[self._segment_hash(text)] = time.time()

    async def process(self, audio_queue: asyncio.Queue):
        """
        Continuously transcribes live audio in 30-second rolling windows,
        posting updates directly to the backend database and publishing to Redis
        so that dashboard clients receive the updates in real time.

        Uses live_transcribe_engine.transcribe_audio_chunk() which applies the
        same verbose_json + 4-layer hallucination filtering as the post-meeting
        pipeline (worker/tasks/transcribe.py _foundry_one).
        """
        if not self.recording_id:
            print("[live_context] No recording_id provided, live transcription disabled", flush=True)
            while True:
                await asyncio.sleep(1)

        import sys

        # Import the shared transcription engine (Foundry verbose_json path).
        # Local faster-whisper does not expose per-segment verbose data so it
        # continues to use the old transcribe_question() path for now.
        if LIVE_WHISPER_BACKEND == "local":
            from local_whisper import transcribe_question, preload
            print(
                "[live_context] Live backend: local faster-whisper "
                "(note: verbose_json filtering not available on local path)",
                file=sys.stderr,
            )
            self._preload_task = asyncio.create_task(preload())
            use_engine = False
        else:
            from live_transcribe_engine import transcribe_audio_chunk
            print(
                "[live_context] Live backend: Azure Foundry Whisper "
                "(verbose_json + hallucination filtering — 30s windows)",
                file=sys.stderr,
            )
            use_engine = True

        redis_url = os.getenv("REDIS_URL", "redis://redis:6379/0")
        backend_url = os.getenv("BACKEND_URL", "http://backend:8000")

        try:
            r_client = redis.Redis.from_url(redis_url)
        except Exception as e:
            print(f"[live_context] Failed to connect to Redis: {e}", file=sys.stderr)
            r_client = None

        loop_start_time_ms = int(time.time() * 1000)
        samples = []
        start_time_ms = loop_start_time_ms
        print(
            f"[live_context] Starting live transcription loop for {self.recording_id} "
            f"(window={_WINDOW_SAMPLES // SAMPLE_RATE}s)",
            file=sys.stderr,
        )
        if not self._lang_locked:
            self._lang_detect_until = time.time() + LIVE_LANG_DETECT_SECONDS
            print(
                f"[live_context] Auto-detecting meeting language for "
                f"{LIVE_LANG_DETECT_SECONDS:.0f}s",
                file=sys.stderr,
            )
        else:
            print(f"[live_context] Language pinned to {self._language}", file=sys.stderr)

        while True:
            try:
                # 32ms chunk size = 512 samples at 16kHz
                chunk = await asyncio.wait_for(audio_queue.get(), timeout=1.0)
                if not samples:
                    start_time_ms = int(time.time() * 1000)
                samples.extend(chunk)
            except asyncio.TimeoutError:
                pass

            # ── Process every 30 seconds (_WINDOW_SAMPLES = 480,000) ────────
            # Larger windows give Whisper more linguistic context, dramatically
            # improving accuracy on code-switched (Hindi/English) speech.
            if len(samples) >= _WINDOW_SAMPLES:
                wav_bytes = _samples_to_wav(samples)
                # Discard the window — no overlap to avoid duplicate segments.
                samples = []

                speaker_name = "Speaker"
                if self.get_speaker_fn:
                    try:
                        speaker_name = self.get_speaker_fn()
                    except Exception as e:
                        print(f"[live_context] Failed to get active speaker: {e}", file=sys.stderr)

                async def _transcribe_and_post(wb, start_time_arg, spk_name):
                    try:
                        if use_engine:
                            # ── New path: verbose_json with 4-layer filtering ──
                            prompt_val = self.settings.get("live_whisper_initial_prompt")
                            segments = await transcribe_audio_chunk(
                                wb, self._language, spk_name, initial_prompt=prompt_val
                            )
                            # Language pinning: if we got real speech segments,
                            # vote and try to finalize. Use the detected language
                            # from the engine (passed back in each segment as
                            # detected_lang when available, else use any non-empty
                            # segment count as a positive vote for the current lang).
                            if not self._lang_locked and segments:
                                detected_for_vote = (
                                    segments[0].get("detected_lang")
                                    or self._language
                                    or "hi"  # Hinglish fallback
                                )
                                self._record_language_vote(detected_for_vote)
                                self._maybe_finalize_language()

                            for seg in segments:
                                text = seg.get("text", "").strip()
                                if not text:
                                    continue

                                # ── Deduplication across 30-second windows ────
                                if self._is_duplicate(text):
                                    continue
                                self._mark_published(text)

                                # Phrase-level hallucination guard (belt-and-suspenders)
                                cleaned = _clean_live_text(text, self._last_live_text)
                                if cleaned is None:
                                    continue
                                self._last_live_text = cleaned

                                if self.get_setting_bool("live_llm_correct", LIVE_LLM_CORRECT):
                                    cleaned = await _llm_clean_live(cleaned)

                                offset_ms = seg.get("offset_ms", 0)
                                duration_ms = seg.get("duration_ms", 0)
                                start_ms = max(0, start_time_arg - loop_start_time_ms) + offset_ms
                                end_ms = start_ms + max(duration_ms, 1000)
                                confidence = seg.get("confidence") or 1.0
                                segment_id = str(uuid.uuid4())

                                await self.add(cleaned, spk_name)

                                async with httpx.AsyncClient(timeout=10) as c:
                                    await c.post(
                                        f"{backend_url}/api/recordings/{self.recording_id}/segments",
                                        json={
                                            "id": segment_id,
                                            "speaker_name": spk_name,
                                            "start_ms": start_ms,
                                            "end_ms": end_ms,
                                            "text": cleaned,
                                            "confidence": confidence,
                                        }
                                    )

                                if r_client:
                                    payload = {
                                        "type": "segment",
                                        "recording_id": self.recording_id,
                                        "segment": {
                                            "id": segment_id,
                                            "speaker_name": spk_name,
                                            "start_ms": start_ms,
                                            "end_ms": end_ms,
                                            "text": cleaned,
                                            "confidence": confidence,
                                        }
                                    }
                                    r_client.publish(
                                        f"zapper:live:{self.recording_id}",
                                        json.dumps(payload),
                                    )

                        else:
                            # ── Legacy path: local faster-whisper (text only) ──
                            # Kept unchanged — local backend lacks verbose_json.
                            if not self._lang_locked:
                                text, detected = await transcribe_question(
                                    wb, return_language=True
                                )
                            else:
                                text = await transcribe_question(wb, language=self._language)
                                detected = None

                            cleaned = _clean_live_text(text if isinstance(text, str) else text[0], self._last_live_text)
                            if cleaned is None:
                                return

                            if not self._lang_locked:
                                if detected and cleaned.strip():
                                    self._record_language_vote(detected)
                                self._maybe_finalize_language()

                            self._last_live_text = cleaned

                            if self.get_setting_bool("live_llm_correct", LIVE_LLM_CORRECT):
                                cleaned = await _llm_clean_live(cleaned)
                            text = cleaned

                            if text and text.strip():
                                if self._is_duplicate(text):
                                    return
                                self._mark_published(text)

                                start_ms = max(0, start_time_arg - loop_start_time_ms)
                                end_ms = start_ms + _WINDOW_SAMPLES // (SAMPLE_RATE // 1000)
                                segment_id = str(uuid.uuid4())

                                await self.add(text, spk_name)

                                async with httpx.AsyncClient(timeout=10) as c:
                                    await c.post(
                                        f"{backend_url}/api/recordings/{self.recording_id}/segments",
                                        json={
                                            "id": segment_id,
                                            "speaker_name": spk_name,
                                            "start_ms": start_ms,
                                            "end_ms": end_ms,
                                            "text": text,
                                            "confidence": 1.0,
                                        }
                                    )

                                if r_client:
                                    payload = {
                                        "type": "segment",
                                        "recording_id": self.recording_id,
                                        "segment": {
                                            "id": segment_id,
                                            "speaker_name": spk_name,
                                            "start_ms": start_ms,
                                            "end_ms": end_ms,
                                            "text": text,
                                            "confidence": 1.0,
                                        }
                                    }
                                    r_client.publish(
                                        f"zapper:live:{self.recording_id}",
                                        json.dumps(payload),
                                    )

                    except Exception as e:
                        print(
                            f"[live_context] Live transcription window failed (continuing): {e}",
                            file=sys.stderr,
                        )

                asyncio.create_task(_transcribe_and_post(wav_bytes, start_time_ms, speaker_name))
                start_time_ms = int(time.time() * 1000)
