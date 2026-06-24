"""
Shared audio-capture wiring for Meet and Teams bots.

Both bots use the SAME audio strategy:

  1) PulseAudio sink monitor → ffmpeg → audio_pulse.wav
  2) WebRTC Insertable Streams JS hook → per-track Opus frames →
     audio_js_t<N>.opus → audio_js_t<N>.wav (decoded at 48 kHz)
  3) After the meeting, mix all per-track JS WAVs into audio_js.wav,
     then pick whichever of {audio_pulse.wav, audio_js.wav} has the
     louder max_volume as the canonical audio.wav.

This module owns (2) and (3) so the orchestration cannot drift between
the two bot implementations.
"""
import asyncio
import audioop
import base64
import os
import struct
import subprocess
import sys
import time
from pathlib import Path


async def setup_opus_capture(
    ctx, 
    recording_id: str, 
    log_prefix: str = "[bot]", 
    track_activity_map: dict = None,
    on_pcm_frame=None
):
    """Wire `window.zapperOpusFrame(trackId, length, b64)` from the page
    into per-track binary Opus stream files on disk.

    Caller is responsible for installing `_JS_AUDIO_INTERCEPTOR` via
    `page.add_init_script()` before navigation.

    Returns (opus_files, opus_path_fn, rec_dir, track_name_map).

    ``track_name_map`` is a dict (initially empty) that the ``zapperTrackName``
    Python callback populates in-place as the JS DOM name poller resolves
    WebRTC track IDs to participant display names during the meeting.
    """
    storage = os.getenv("STORAGE_PATH", "/data/recordings")
    rec_dir = str(Path(storage) / recording_id)
    os.makedirs(rec_dir, exist_ok=True)

    opus_files: dict[str, object] = {}
    opus_counts: dict[str, int] = {}
    opus_bytes: dict[str, int] = {}
    
    # Decoders for real-time PCM extraction
    decoders = {}

    def _opus_path(track_id: str) -> str:
        return os.path.join(rec_dir, f"audio_js_{track_id}.opus")

    async def _receive_opus_frame(track_id: str, length: int, b64: str) -> None:
        try:
            pkt = base64.b64decode(b64)
            if track_activity_map is not None:
                import time
                if track_id not in track_activity_map:
                    track_activity_map[track_id] = []
                track_activity_map[track_id].append(time.time())
            fh = opus_files.get(track_id)
            if fh is None:
                fh = open(_opus_path(track_id), "wb")
                opus_files[track_id] = fh
                opus_counts[track_id] = 0
                opus_bytes[track_id] = 0
                print(
                    f"{log_prefix} opening opus stream file for {track_id}",
                    file=sys.stderr,
                )
            fh.write(struct.pack("<I", len(pkt)))
            fh.write(pkt)
            opus_counts[track_id] += 1
            opus_bytes[track_id] += len(pkt)
            if opus_counts[track_id] % 500 == 0:
                print(
                    f"{log_prefix} {track_id}: {opus_counts[track_id]} opus frames "
                    f"({opus_bytes[track_id] / 1024:.1f} KB)",
                    file=sys.stderr,
                )
                
            # Real-time decoding and callback for LIVE_PER_TRACK
            if on_pcm_frame is not None:
                import opuslib
                if track_id not in decoders:
                    # 48 kHz, mono
                    decoders[track_id] = opuslib.Decoder(48000, 1)
                try:
                    # Decode to 48kHz 16-bit PCM bytes
                    pcm_bytes = decoders[track_id].decode(pkt, 5760, decode_fec=False)
                    
                    if not hasattr(decoders[track_id], "_z_last_time"):
                        decoders[track_id]._z_last_time = time.time()
                        decoders[track_id]._z_ratecv_state = None
                        
                    # Downsample properly to avoid aliasing and robotic audio
                    resampled_bytes, decoders[track_id]._z_ratecv_state = audioop.ratecv(
                        pcm_bytes, 2, 1, 48000, 16000, decoders[track_id]._z_ratecv_state
                    )
                    
                    # Unpack to integers
                    num_samples = len(resampled_bytes) // 2
                    samples_16k_raw = list(struct.unpack(f"<{num_samples}h", resampled_bytes))
                        
                    now = time.time()
                    diff = now - decoders[track_id]._z_last_time
                    if diff > 0.15:
                        silence_sec = min(diff, 10.0)
                        silence_samples = [0] * int(silence_sec * 16000)
                        samples_16k = silence_samples + samples_16k_raw
                    else:
                        samples_16k = samples_16k_raw
                    
                    decoders[track_id]._z_last_time = now
                    
                    # Fire callback
                    if asyncio.iscoroutinefunction(on_pcm_frame):
                        await on_pcm_frame(track_id, samples_16k)
                    else:
                        on_pcm_frame(track_id, samples_16k)
                except Exception as decode_err:
                    if "corrupted stream" not in str(decode_err).lower():
                        print(f"{log_prefix} opus real-time decode error for {track_id}: {decode_err}", file=sys.stderr)
                    silence_16k = [0] * 320  # 20ms at 16kHz
                    now = time.time()
                    if track_id in decoders:
                        decoders[track_id]._z_last_time = now
                    if asyncio.iscoroutinefunction(on_pcm_frame):
                        await on_pcm_frame(track_id, silence_16k)
                    else:
                        on_pcm_frame(track_id, silence_16k)
                    
        except Exception as exc:
            print(f"{log_prefix} opus frame error: {exc}", file=sys.stderr)

    await ctx.expose_function("zapperOpusFrame", _receive_opus_frame)

    # Track → participant name map populated by the JS DOM name poller.
    track_name_map: dict[str, str] = {}

    # Bot display name — used to filter out the bot's own audio track.
    _bot_display_name = (os.getenv("BOT_DISPLAY_NAME") or "Zapper Recorder").strip().lower()

    async def _receive_track_name(track_id: str, name: str) -> None:
        name = (name or "").strip()
        if not track_id or not name:
            return
        # Skip the bot's own display name — we only want real participant names.
        if name.lower() == _bot_display_name or "zapper" in name.lower():
            return
        old = track_name_map.get(track_id)
        if old == name:
            return  # no change
        track_name_map[track_id] = name
        if old:
            print(
                f"{log_prefix} DOM name updated: {track_id} '{old}' → '{name}'",
                file=sys.stderr,
            )
        else:
            print(
                f"{log_prefix} DOM name resolved: {track_id} → '{name}'",
                file=sys.stderr,
            )

    await ctx.expose_function("zapperTrackName", _receive_track_name)

    return opus_files, _opus_path, rec_dir, track_name_map


def _max_volume(path: str) -> float:
    """Return ffmpeg's max_volume (dB) for a WAV file, or -inf on error."""
    if not os.path.exists(path):
        return float("-inf")
    try:
        out = subprocess.run(
            ["ffmpeg", "-i", path, "-af", "volumedetect", "-f", "null", "-"],
            capture_output=True, text=True,
        )
        for line in out.stderr.splitlines():
            if "max_volume" in line:
                return float(line.split("max_volume:")[1].split("dB")[0].strip())
    except Exception:
        pass
    return float("-inf")


def finalize_audio(
    *,
    capture_wav_path: str,
    rec_dir: str,
    opus_files: dict,
    opus_path_fn,
    log_prefix: str = "[bot]",
    track_name_map: dict | None = None,
) -> str:
    """Run after the meeting ends, after capture.stop():

    - Move ffmpeg's output to audio_pulse.wav
    - Decode all per-track Opus streams to audio_js_t<N>.wav (48 kHz)
    - Mix per-track WAVs into audio_js.wav (16 kHz mono s16)
    - Pick the louder of (audio_pulse, audio_js) as canonical audio.wav

    Returns the canonical wav_path that should be uploaded to the API.
    """
    pulse_wav = os.path.join(rec_dir, "audio_pulse.wav")
    js_wav = os.path.join(rec_dir, "audio_js.wav")

    # Preserve the PulseAudio capture under its own name.
    try:
        if os.path.exists(capture_wav_path):
            os.replace(capture_wav_path, pulse_wav)
            print(f"{log_prefix} PulseAudio capture saved: {pulse_wav}", file=sys.stderr)
    except Exception as exc:
        print(f"{log_prefix} preserve pulse wav failed: {exc}", file=sys.stderr)

    # Close per-track Opus stream files.
    for fh in list(opus_files.values()):
        try:
            fh.close()
        except Exception:
            pass

    # Decode every Opus stream to a WAV.
    if opus_files:
        from opus_decoder import decode_opus_file
        track_wavs: list[str] = []
        for track_id in opus_files:
            opus_path = opus_path_fn(track_id)
            track_wav = os.path.join(rec_dir, f"audio_js_{track_id}.wav")
            try:
                decoded, failed = decode_opus_file(opus_path, track_wav)
                size_kb = os.path.getsize(track_wav) / 1024 if os.path.exists(track_wav) else 0
                print(
                    f"{log_prefix} {track_id}: decoded {decoded} frames "
                    f"({failed} failed) → {track_wav} ({size_kb:.1f} KB)",
                    file=sys.stderr,
                )
                if decoded > 0:
                    track_wavs.append(track_wav)
            except Exception as exc:
                print(f"{log_prefix} opus decode failed for {track_id}: {exc}", file=sys.stderr)

        # Mix per-track WAVs into one 16k mono WAV.
        if track_wavs:
            try:
                if len(track_wavs) == 1:
                    cmd = [
                        "ffmpeg", "-y", "-i", track_wavs[0],
                        "-ar", "16000", "-ac", "1", "-sample_fmt", "s16",
                        js_wav,
                    ]
                else:
                    cmd = ["ffmpeg", "-y"]
                    for p in track_wavs:
                        cmd += ["-i", p]
                    cmd += [
                        "-filter_complex",
                        f"amix=inputs={len(track_wavs)}:duration=longest:normalize=0",
                        "-ar", "16000", "-ac", "1", "-sample_fmt", "s16",
                        js_wav,
                    ]
                result = subprocess.run(cmd, capture_output=True, text=True)
                if result.returncode == 0:
                    print(
                        f"{log_prefix} JS audio → WAV OK ({len(track_wavs)} tracks): {js_wav}",
                        file=sys.stderr,
                    )
                else:
                    print(
                        f"{log_prefix} ffmpeg mix failed:\n{result.stderr[-800:]}",
                        file=sys.stderr,
                    )
            except Exception as exc:
                print(f"{log_prefix} JS audio save error: {exc}", file=sys.stderr)
        else:
            print(f"{log_prefix} No usable decoded WAVs", file=sys.stderr)
    else:
        print(f"{log_prefix} No JS opus frames captured", file=sys.stderr)

    # Pick the louder of (pulse, js) as canonical audio.wav.
    pulse_db = _max_volume(pulse_wav)
    js_db = _max_volume(js_wav)
    print(f"{log_prefix} max_volume pulse={pulse_db} dB  js={js_db} dB", file=sys.stderr)

    winner = pulse_wav if pulse_db >= js_db else js_wav
    if os.path.exists(winner):
        import shutil
        shutil.copy(winner, capture_wav_path)
        print(f"{log_prefix} Winner: {winner} → {capture_wav_path}", file=sys.stderr)

    # Write track_names.json so the match_speakers worker can use DOM-resolved
    # names as the primary source (no voice-embedding lookup required).
    if track_name_map is not None:
        try:
            import json as _json
            track_names_path = os.path.join(rec_dir, "track_names.json")
            with open(track_names_path, "w") as _tf:
                _json.dump(track_name_map, _tf)
            if track_name_map:
                print(
                    f"{log_prefix} track_names.json written: {track_name_map}",
                    file=sys.stderr,
                )
            else:
                print(
                    f"{log_prefix} track_names.json written (empty — DOM name resolution found nothing)",
                    file=sys.stderr,
                )
        except Exception as exc:
            print(f"{log_prefix} Failed to write track_names.json: {exc}", file=sys.stderr)

    return capture_wav_path
