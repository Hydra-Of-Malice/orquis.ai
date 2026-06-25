"""
Transcription task — dual backend (Azure Foundry Whisper + local faster-whisper).
Ported from zapper/worker/tasks/transcribe.py — no external dependency.
"""
import glob
import math
import os
import subprocess
import tempfile
import wave

import httpx
from sqlalchemy import text
from db import get_session

STORAGE_PATH = os.getenv("STORAGE_PATH", "/data/recordings")
WHISPER_MODEL = os.getenv("WHISPER_MODEL", "small")
WHISPER_LANGUAGE = (os.getenv("WHISPER_LANGUAGE", "").strip() or None)
WHISPER_DEVICE = os.getenv("WHISPER_DEVICE", "cpu")
WHISPER_COMPUTE = os.getenv("WHISPER_COMPUTE", "int8")
MIN_SEGMENT_CONFIDENCE = float(os.getenv("WHISPER_MIN_CONFIDENCE", "0.37"))

FOUNDRY_ENDPOINT = os.getenv("AZURE_FOUNDRY_ENDPOINT", "").strip()
FOUNDRY_KEY = os.getenv("AZURE_FOUNDRY_KEY", "").strip()
FOUNDRY_WHISPER_DEPLOYMENT = os.getenv("AZURE_FOUNDRY_WHISPER_DEPLOYMENT", "whisper").strip()
FOUNDRY_API_VERSION = os.getenv("AZURE_FOUNDRY_WHISPER_API_VERSION", "2024-06-01")
WHISPER_BACKEND = os.getenv("WHISPER_BACKEND", "auto").strip().lower()
FOUNDRY_MAX_UPLOAD_BYTES = 24 * 1024 * 1024
FOUNDRY_MP3_BITRATE = os.getenv("FOUNDRY_MP3_BITRATE", "64k")

_LANG_NAME_TO_ISO = {
    "hindi": "hi", "english": "en", "spanish": "es", "french": "fr",
    "german": "de", "portuguese": "pt", "italian": "it", "dutch": "nl",
    "russian": "ru", "arabic": "ar", "chinese": "zh", "japanese": "ja",
    "korean": "ko", "turkish": "tr", "polish": "pl", "swedish": "sv",
    "norwegian": "no", "danish": "da", "finnish": "fi", "czech": "cs",
    "hungarian": "hu", "romanian": "ro", "mandarin": "zh", "urdu": "ur",
}

_MODEL = None  # lazy-loaded faster-whisper singleton


def _normalize_lang(lang: str | None) -> str | None:
    if not lang:
        return None
    s = lang.strip().lower()
    if 2 <= len(s) <= 3 and s.isalpha():
        return s
    return _LANG_NAME_TO_ISO.get(s)


def _use_foundry() -> bool:
    if WHISPER_BACKEND == "foundry":
        return True
    if WHISPER_BACKEND == "local":
        return False
    return bool(FOUNDRY_ENDPOINT and FOUNDRY_KEY and FOUNDRY_WHISPER_DEPLOYMENT)


def _get_model():
    global _MODEL
    if _MODEL is None:
        from faster_whisper import WhisperModel
        print(f"[transcribe] Loading faster-whisper model={WHISPER_MODEL} device={WHISPER_DEVICE}", flush=True)
        _MODEL = WhisperModel(WHISPER_MODEL, device=WHISPER_DEVICE, compute_type=WHISPER_COMPUTE)
        print("[transcribe] Model loaded", flush=True)
    return _MODEL


def _check_wav(wav_path: str):
    size = os.path.getsize(wav_path)
    print(f"[transcribe] WAV size: {size/1024/1024:.2f} MB  path={wav_path}", flush=True)
    try:
        with wave.open(wav_path, "rb") as wf:
            frames = wf.getnframes()
            if frames == 0:
                raise ValueError("WAV has 0 frames — audio capture produced silence")
    except wave.Error as exc:
        raise ValueError(f"Cannot read WAV header: {exc}")


def _compress_for_foundry(wav_path: str) -> str:
    fd, mp3_path = tempfile.mkstemp(suffix=".mp3", prefix="zapper_pm_")
    os.close(fd)
    cmd = ["ffmpeg", "-y", "-i", wav_path, "-vn", "-ac", "1", "-ar", "16000", "-b:a", FOUNDRY_MP3_BITRATE, mp3_path]
    res = subprocess.run(cmd, capture_output=True, text=True)
    if res.returncode != 0:
        try:
            os.unlink(mp3_path)
        except OSError:
            pass
        raise RuntimeError(f"ffmpeg failed: {res.stderr[-400:]}")
    return mp3_path


def _foundry_detect_language(wav_path: str) -> str | None:
    fd, snippet = tempfile.mkstemp(suffix=".mp3", prefix="zapper_pm_lang_")
    os.close(fd)
    try:
        cmd = ["ffmpeg", "-y", "-i", wav_path, "-vn", "-ac", "1", "-ar", "16000", "-t", "60", "-b:a", "32k", snippet]
        res = subprocess.run(cmd, capture_output=True, text=True)
        if res.returncode != 0:
            return None
        url = f"{FOUNDRY_ENDPOINT.rstrip('/')}/openai/deployments/{FOUNDRY_WHISPER_DEPLOYMENT}/audio/transcriptions?api-version={FOUNDRY_API_VERSION}"
        with open(snippet, "rb") as fh:
            files = {"file": (os.path.basename(snippet), fh, "audio/mpeg")}
            with httpx.Client(timeout=120) as client:
                r = client.post(url, headers={"api-key": FOUNDRY_KEY}, files=files, data={"response_format": "verbose_json"})
        if r.status_code != 200:
            return None
        raw_lang = (r.json() or {}).get("language")
        lang = _normalize_lang(raw_lang)
        print(f"[transcribe] Language probe: {raw_lang!r} → {lang!r}", flush=True)
        return lang
    except Exception as exc:
        print(f"[transcribe] Language probe failed: {exc}", flush=True)
        return None
    finally:
        try:
            os.unlink(snippet)
        except OSError:
            pass


def _foundry_one(wav_path: str, speaker_id: str, language: str | None) -> list[dict]:
    print(f"[transcribe] {speaker_id} ← {wav_path}  backend=foundry  lang={language or 'auto'}", flush=True)
    mp3_path = _compress_for_foundry(wav_path)
    try:
        size = os.path.getsize(mp3_path)
        if size > FOUNDRY_MAX_UPLOAD_BYTES:
            raise RuntimeError(f"Audio too large ({size/1024/1024:.1f}MB) — exceeds Foundry 25MB limit")
        url = f"{FOUNDRY_ENDPOINT.rstrip('/')}/openai/deployments/{FOUNDRY_WHISPER_DEPLOYMENT}/audio/transcriptions?api-version={FOUNDRY_API_VERSION}"
        data = {"response_format": "verbose_json"}
        if language:
            data["language"] = language
        with open(mp3_path, "rb") as fh:
            files = {"file": (os.path.basename(mp3_path), fh, "audio/mpeg")}
            with httpx.Client(timeout=600) as client:
                r = client.post(url, headers={"api-key": FOUNDRY_KEY}, files=files, data=data)
        if r.status_code != 200:
            raise RuntimeError(f"Foundry HTTP {r.status_code}: {r.text[:400]}")
        body = r.json()
    finally:
        try:
            os.unlink(mp3_path)
        except OSError:
            pass

    raw_segments = body.get("segments") or []
    out: list[dict] = []
    last_text = None
    for seg in raw_segments:
        text_clean = (seg.get("text") or "").strip()
        if not text_clean:
            continue
        avg_logprob = seg.get("avg_logprob")
        no_speech_prob = float(seg.get("no_speech_prob") or 0)
        compression_ratio = float(seg.get("compression_ratio") or 1.0)

        if no_speech_prob > 0.6 and isinstance(avg_logprob, (int, float)) and avg_logprob < -1.0:
            continue
        if compression_ratio > 2.4:
            continue
        confidence = math.exp(avg_logprob) if isinstance(avg_logprob, (int, float)) else None
        if confidence is not None and confidence < MIN_SEGMENT_CONFIDENCE:
            continue
        if text_clean == last_text:
            continue
        last_text = text_clean
        start = float(seg.get("start", 0.0))
        end = float(seg.get("end", start))
        out.append({
            "speaker_id": speaker_id,
            "text": text_clean,
            "offset_ms": int(start * 1000),
            "start_ms": int(start * 1000),
            "end_ms": int(end * 1000),
            "duration_ms": int(max(0.0, end - start) * 1000),
            "confidence": confidence,
        })
    print(f"[transcribe] {speaker_id}: foundry → {len(out)} segments", flush=True)
    return out


def _whisper_one(model, wav_path: str, speaker_id: str, language: str | None) -> list[dict]:
    print(f"[transcribe] {speaker_id} ← {wav_path}  lang={language or 'auto'}", flush=True)
    segments_iter, info = model.transcribe(
        wav_path,
        language=language,
        vad_filter=True,
        beam_size=5,
        no_speech_threshold=0.6,
        log_prob_threshold=-1.0,
        compression_ratio_threshold=2.4,
        condition_on_previous_text=False,
    )
    out: list[dict] = []
    last_text = None
    for seg in segments_iter:
        text_clean = seg.text.strip()
        if not text_clean:
            continue
        confidence = math.exp(seg.avg_logprob) if seg.avg_logprob is not None else None
        if confidence is not None and confidence < MIN_SEGMENT_CONFIDENCE:
            continue
        if text_clean == last_text:
            continue
        last_text = text_clean
        out.append({
            "speaker_id": speaker_id,
            "text": text_clean,
            "offset_ms": int(seg.start * 1000),
            "start_ms": int(seg.start * 1000),
            "end_ms": int(seg.end * 1000),
            "duration_ms": int((seg.end - seg.start) * 1000),
            "confidence": confidence,
        })
    print(f"[transcribe] {speaker_id}: local whisper → {len(out)} segments", flush=True)
    return out


def transcribe_recording(meeting_id: str) -> list[dict]:
    """Transcribe audio files, returns list of segment dicts."""
    with get_session() as session:
        row = session.execute(
            text("SELECT wav_path FROM meetings WHERE id = :id"),
            {"id": meeting_id},
        ).fetchone()

    if not row or not row[0]:
        raise ValueError(f"No WAV path for meeting {meeting_id}")

    wav_path = row[0]
    if wav_path.startswith("http"):
        raise ValueError(f"WAV is on Azure — cannot transcribe from URL directly")

    _check_wav(wav_path)

    use_foundry = _use_foundry()
    print(f"[transcribe] Backend: {'Azure Foundry Whisper' if use_foundry else 'local faster-whisper'}", flush=True)
    model = None if use_foundry else _get_model()
    rec_dir = os.path.dirname(wav_path)

    def _nat_key(p: str) -> list:
        return [int(c) if c.isdigit() else c for c in re.split(r"(\d+)", os.path.basename(p))]

    import re
    track_wavs = sorted(glob.glob(os.path.join(rec_dir, "audio_js_t*.wav")), key=_nat_key)

    # Pin language once for consistency
    pinned_lang = _normalize_lang(WHISPER_LANGUAGE) or WHISPER_LANGUAGE
    if not pinned_lang:
        candidates = list(track_wavs) + ([wav_path] if os.path.exists(wav_path) else [])
        candidates = [c for c in candidates if os.path.getsize(c) >= 50 * 1024]
        if candidates:
            biggest = max(candidates, key=os.path.getsize)
            if use_foundry:
                pinned_lang = _foundry_detect_language(biggest)
            else:
                try:
                    _segs, info = model.transcribe(biggest, vad_filter=True, beam_size=1, no_speech_threshold=0.6, condition_on_previous_text=False)
                    del _segs
                    pinned_lang = getattr(info, "language", None)
                except Exception:
                    pass
    print(f"[transcribe] Pinned language: {pinned_lang or '(auto)'}", flush=True)

    def _transcribe_one(wav: str, speaker: str) -> list[dict]:
        if use_foundry:
            try:
                return _foundry_one(wav, speaker, pinned_lang)
            except Exception as exc:
                print(f"[transcribe] Foundry failed for {speaker} ({exc}) — falling back to local", flush=True)
                local = _get_model()
                return _whisper_one(local, wav, speaker, pinned_lang)
        return _whisper_one(model, wav, speaker, pinned_lang)

    segments: list[dict] = []

    if track_wavs:
        print(f"[transcribe] Per-track diarization — {len(track_wavs)} track(s)", flush=True)
        speaker_idx = 0
        for tw in track_wavs:
            if os.path.getsize(tw) < 50 * 1024:
                print(f"[transcribe] Skipping {tw} (too small)", flush=True)
                continue
            speaker_id = f"Speaker_{chr(ord('A') + speaker_idx)}"
            speaker_idx += 1
            try:
                segments.extend(_transcribe_one(tw, speaker_id))
            except Exception as exc:
                print(f"[transcribe] WARN per-track {tw} failed: {exc}", flush=True)
        segments.sort(key=lambda s: s["start_ms"])
    else:
        print("[transcribe] No per-track WAVs — using mixed audio", flush=True)

    if not segments:
        segments = _transcribe_one(wav_path, "Speaker_A")

    # Save to DB
    with get_session() as session:
        session.execute(
            text("DELETE FROM transcript_segments WHERE meeting_id = :id"),
            {"id": meeting_id},
        )
        for seg in segments:
            session.execute(
                text("""
                    INSERT INTO transcript_segments
                        (id, meeting_id, speaker_name, speaker_id,
                         start_ms, end_ms, text, confidence)
                    VALUES
                        (gen_random_uuid(), :meeting_id, :speaker, :speaker_id,
                         :start_ms, :end_ms, :text, :confidence)
                """),
                {
                    "meeting_id": meeting_id,
                    "speaker": seg.get("speaker_id", "Speaker_A"),
                    "speaker_id": seg.get("speaker_id"),
                    "start_ms": seg.get("start_ms", 0),
                    "end_ms": seg.get("end_ms", 0),
                    "text": seg.get("text", ""),
                    "confidence": seg.get("confidence"),
                },
            )
        session.commit()

    print(f"[transcribe] Done — {len(segments)} segments saved for {meeting_id}", flush=True)
    return segments
