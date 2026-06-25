"""
Microsoft Teams bot — Playwright orchestrator with full parity to MeetBot.

End-to-end flow:
  1. Launch Chromium with WebRTC Insertable Streams enabled.
  2. (Optional) sign into Microsoft account using BOT_MS_EMAIL / BOT_MS_PASSWORD.
  3. Navigate to the Teams meeting URL using `domcontentloaded` (Teams web
     never reaches networkidle).
  4. Pre-join: dismiss UI prompts, fill display name, mute mic, turn off
     camera, click the join button. Screenshots saved at every step.
  5. Wait in the lobby until admitted using SIX detection strategies
     (data-tid hangup, accessible-name buttons, CSS variants, URL
     heuristics, "Join now" gone, JS-eval check).
  6. Run capture + scraper + wake-word + live-buffer + controller as
     BACKGROUND tasks so we can cancel them when the meeting ends.
  7. `_watch_for_end` foreground-await with 4 detection strategies:
     end-text, navigated away, hangup-button gone, "alone after peak"
     for `MAX_ALONE_SECONDS` (gated by `MIN_MEETING_SECONDS`).
  8. Stop ffmpeg, finalize audio (PulseAudio + per-track Opus → mix →
     louder-wins) via the shared bot_audio_pipeline.
"""
import asyncio
import json
import os
import sys
import time
import uuid
from typing import Any

import httpx
import redis as _redis_module

import yaml
from playwright.async_api import async_playwright, Page, TimeoutError as PWTimeout

from audio_setup import BotEnvironment, create_bot_environment
from audio_capture import AudioCapture
from audio_output import AudioOutput
from scraper import ParticipantScraper
from live_context import LiveTranscriptBuffer
from meeting_controller import MeetingController
from bot_api_client import BotAPIClient

# Reuse the JS interceptor from MeetBot — it's codec-level and works for
# any WebRTC client that uses RTCPeerConnection (Teams included).
from meet_bot import _JS_AUDIO_INTERCEPTOR
from bot_audio_pipeline import setup_opus_capture, finalize_audio

with open("config/selectors.yaml") as f:
    SEL = yaml.safe_load(f)

BOT_DISPLAY_NAME = os.getenv("BOT_DISPLAY_NAME", "Zapper Recorder")
LOBBY_TIMEOUT = int(os.getenv("BOT_LOBBY_TIMEOUT_SECONDS", "300"))
MIN_MEETING_SECONDS = int(os.getenv("BOT_MIN_MEETING_SECONDS", "120"))
MAX_ALONE_SECONDS = int(os.getenv("BOT_MAX_ALONE_SECONDS", "60"))


class TeamsBot:
    def __init__(self, recording_id: str, meeting_url: str, slot: int, settings: dict | None = None):
        self.recording_id = recording_id
        self.meeting_url = meeting_url
        self.slot = slot
        self.settings = settings or {}
        self.env: BotEnvironment = create_bot_environment(slot)
        self.participants: list[str] = []
        self._participants_seen: set[str] = set()
        self.api = BotAPIClient(recording_id)
        self.audio_q: asyncio.Queue = asyncio.Queue(maxsize=1000)
        self.live_q: asyncio.Queue = asyncio.Queue(maxsize=1000)
        # Debounce table: speaker → pending asyncio.Task
        self._pending_caption_tasks: dict[str, asyncio.Task] = {}
        # Shared Redis client for live caption publishing (created lazily).
        self._caption_redis: Any = None  # redis.Redis at runtime; Any avoids .publish false-positive

        self.bot_display_name: str = str(self.get_setting("bot_name", "BOT_DISPLAY_NAME", "Zapper Recorder"))
        self.lobby_timeout: int = int(self.get_setting("lobby_timeout_seconds", "BOT_LOBBY_TIMEOUT_SECONDS", 300, type_cast=int))
        self.min_meeting_seconds: int = int(self.get_setting("min_meeting_seconds", "BOT_MIN_MEETING_SECONDS", 120, type_cast=int))
        self.max_alone_seconds: int = int(self.get_setting("max_alone_seconds", "BOT_MAX_ALONE_SECONDS", 60, type_cast=int))
        self.auto_leave_when_alone: bool = bool(self.get_setting("auto_leave_when_alone", "BOT_AUTO_LEAVE_WHEN_ALONE", True, type_cast=bool))
        # Visual capture mode — set per-meeting in the "Record a meeting" modal.
        self.visual_capture_mode: str = str(
            self.get_setting("visual_capture_mode", "VISUAL_CAPTURE_MODE", "disabled")
        ).strip().lower()

    def get_setting(self, key: str, env_var: str, default, type_cast=str) -> "bool | int | str":
        val = self.settings.get(key)
        if val is None:
            val = os.getenv(env_var)
        if val is None:
            val = default
        
        if type_cast == bool:
            if isinstance(val, bool):
                return val
            return str(val).lower() in ("true", "1", "yes", "on")
        elif type_cast == int:
            return int(val)
        return str(val)

    async def _fanout_audio(self):
        while True:
            try:
                samples = await self.audio_q.get()
                try:
                    self.live_q.put_nowait(samples)
                except asyncio.QueueFull:
                    pass
            except asyncio.CancelledError:
                break
            except Exception:
                await asyncio.sleep(0.1)

    async def _on_scraper_participants(self, names: list[str]):
        bot_env_name = self.bot_display_name.strip().lower()
        updated = False
        for n in names:
            n_clean = n.strip()
            if not n_clean:
                continue
            nl = n_clean.lower()
            if nl == bot_env_name:
                continue
            if nl in {"you", "(you)"}:
                continue
            if n_clean not in self._participants_seen:
                self._participants_seen.add(n_clean)
                self.participants.append(n_clean)
                print(f"[teams-bot] Participant detected via scraper: {n_clean}", file=sys.stderr)
                updated = True
        if updated:
            await self.api.update_participants(self.participants)

    # ────────────────────────────────────────────────────────────────────
    # Main run loop
    # ────────────────────────────────────────────────────────────────────
    async def run(self):
        await self.api.update_status("joining")
        async with async_playwright() as pw:
            chromium_env = {**os.environ}
            chromium_env["DISPLAY"] = f":{self.env.display_num}"
            chromium_env["PULSE_SERVER"] = f"unix:{self.env.pulse_socket}"
            chromium_env["PULSE_SINK"] = self.env.sink_name
            chromium_env["PULSE_SOURCE"] = f"{self.env.sink_name}.monitor"

            browser = await pw.chromium.launch(
                executable_path="/usr/bin/chromium",
                headless=False,
                args=[
                    f"--display=:{self.env.display_num}",
                    "--no-sandbox",
                    "--disable-setuid-sandbox",
                    "--use-fake-ui-for-media-stream",
                    "--use-fake-device-for-media-stream",
                    "--use-file-for-fake-audio-capture=/opt/silence.wav",
                    "--enable-blink-features=WebRTCInsertableStreams,RTCRtpScriptTransform",
                    "--enable-features=RTCEncodedTransform",
                    "--autoplay-policy=no-user-gesture-required",
                    "--disable-features=AudioServiceSandbox,AudioServiceOutOfProcess",
                    "--disable-blink-features=AutomationControlled",
                    "--disable-gpu",
                    "--disable-dev-shm-usage",
                ],
                env={k: v for k, v in chromium_env.items()},  # type: ignore[arg-type]
            )

            session_path = os.getenv(
                "BOT_MS_SESSION_PATH", "/data/recordings/ms_session.json"
            )
            ctx_kwargs: dict = dict(
                permissions=["microphone", "camera"],
                user_agent=(
                    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
                    "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36 Edg/124.0.0.0"
                ),
                viewport={"width": 1280, "height": 900},
                locale="en-US",
            )
            if os.path.exists(session_path):
                ctx_kwargs["storage_state"] = session_path
                print(f"[teams-bot] Loading saved MS session from {session_path}", file=sys.stderr)

            ctx = await browser.new_context(**ctx_kwargs)

            track_activity_map = {}
            from live_context import LiveTranscriptBuffer, get_active_speaker_name
            
            _live_engine = str(self.get_setting("live_engine", "LIVE_ENGINE", "captions")).strip().lower()
            if _live_engine not in ("captions", "whisper", "both"):
                print(f"[teams-bot] Unknown LIVE_ENGINE={_live_engine!r}; defaulting to 'captions'", file=sys.stderr)
                _live_engine = "captions"
            _run_whisper = _live_engine in ("whisper", "both")
            _captions_post = _live_engine in ("captions", "both")
            _live_per_track = self.get_setting("live_per_track", "LIVE_PER_TRACK", False, type_cast=bool)

            track_name_map = {}
            def _get_master_speaker():
                name = get_active_speaker_name(track_activity_map, track_name_map)
                # If the resolved name is not a known participant (e.g. it's the
                # bot's own account name), demote to 'Speaker' so the 1-participant
                # fallback can fire and return the real participant's name.
                if name != "Speaker" and self.participants and name not in self.participants:
                    name = "Speaker"
                if name == "Speaker" and len(self.participants) == 1:
                    return self.participants[0]
                return name
                
            live_buf = LiveTranscriptBuffer(recording_id=self.recording_id, get_speaker_fn=_get_master_speaker, settings=self.settings)

            track_buffers = {}
            track_queues = {}
            dynamic_tasks = []
            
            # Use a mutable wrapper so _on_pcm_frame can access the dynamically populated map
            track_name_state = {"map": track_name_map}
            
            async def _on_pcm_frame(track_id, samples_16k):
                if track_id not in track_buffers:
                    q = asyncio.Queue(maxsize=1000)
                    track_queues[track_id] = q
                    def _get_spk(_t=track_id):
                        name = track_name_state["map"].get(_t, "")
                        return name if name else "Speaker"
                    t_buf = LiveTranscriptBuffer(
                        recording_id=self.recording_id, 
                        get_speaker_fn=_get_spk,
                        master_buf=live_buf,
                        settings=self.settings
                    )
                    track_buffers[track_id] = t_buf
                    if _run_whisper:
                        t = asyncio.create_task(t_buf.process(q))
                        dynamic_tasks.append(t)
                        print(f"[teams-bot] Started LIVE_PER_TRACK Whisper pipeline for {track_id}", file=sys.stderr)
                try:
                    track_queues[track_id].put_nowait(samples_16k)
                except asyncio.QueueFull:
                    pass

            # Wire per-track Opus capture from the JS interceptor.
            opus_files, opus_path_fn, rec_dir, _name_map = await setup_opus_capture(
                ctx, self.recording_id, log_prefix="[teams-bot]", 
                track_activity_map=track_activity_map,
                on_pcm_frame=_on_pcm_frame if _live_per_track else None
            )
            track_name_state["map"] = _name_map
            track_name_map = _name_map

            page = await ctx.new_page()
            page.on("console", lambda msg: print(
                f"[browser] {msg.type}: {msg.text}", file=sys.stderr
            ) if "[zapper]" in msg.text else None)

            # Inject RTC interceptor BEFORE any Teams JS runs.
            await page.add_init_script(_JS_AUDIO_INTERCEPTOR)

            caption_events = []

            _backend_url = os.getenv("BACKEND_URL", "http://backend:8000")
            _redis_url   = os.getenv("REDIS_URL",   "redis://redis:6379/0")

            # Lazily initialise Redis client once.
            try:
                self._caption_redis = _redis_module.Redis.from_url(_redis_url)
            except Exception as _re:
                print(f"[teams-bot] Redis init failed (live captions won't stream): {_re}", file=sys.stderr)
                self._caption_redis = None

            async def _finalize_caption(speaker: str, text: str, start_ms: int) -> None:
                """Post a finalized caption segment to backend + Redis for live display."""
                seg_id = str(uuid.uuid4())
                seg = {
                    "id": seg_id,
                    "speaker_name": speaker,
                    "start_ms": start_ms,
                    "end_ms": start_ms + 5000,   # generous end — we don't know exact duration
                    "text": text,
                    "confidence": 1.0,
                }
                # Feed into rolling live-context buffer for wake-word Q&A.
                # When Whisper is the live engine it already populates live_buf
                # via process(), so captions must not double-populate it.
                if not _run_whisper:
                    try:
                        await live_buf.add(text, speaker)
                    except Exception:
                        pass
                # In whisper-only mode captions are archived to captions.json
                # (see _on_caption_event) but must not drive the live transcript.
                if not _captions_post:
                    return
                # POST to backend so the segment is persisted + returned on page reload.
                try:
                    async with httpx.AsyncClient(timeout=8) as _c:
                        r = await _c.post(
                            f"{_backend_url}/api/recordings/{self.recording_id}/segments",
                            json=seg,
                        )
                        if r.status_code not in (200, 201):
                            print(f"[teams-bot] Caption segment POST {r.status_code}: {r.text[:120]}", file=sys.stderr)
                        else:
                            print(f"[teams-bot] Caption posted: {speaker!r} → {text[:60]!r}", file=sys.stderr)
                except Exception as _exc:
                    print(f"[teams-bot] Caption segment POST failed: {_exc}", file=sys.stderr)
                # Publish to Redis so the WebSocket pushes it to the dashboard instantly.
                if self._caption_redis:
                    try:
                        payload = json.dumps({
                            "type": "segment",
                            "recording_id": self.recording_id,
                            "segment": seg,
                        })
                        self._caption_redis.publish(f"zapper:live:{self.recording_id}", payload)  # type: ignore[union-attr]
                    except Exception as _exc:
                        print(f"[teams-bot] Caption Redis publish failed: {_exc}", file=sys.stderr)

            async def _on_caption_event(speaker: str, text: str, timestamp_ms: float):
                """Called by the JS caption observer for every unique (speaker, text) pair.

                Teams streams partial captions (e.g. 'Button' → 'Button button' → 'Button,
                button, terminal it is showing.')  We debounce 2 s per speaker so only the
                *last* text for a continuous utterance is posted, not every partial update.
                """
                # Compute recording-relative offset.
                start_ms = 0
                if hasattr(self, 'recording_start_time_ms') and self.recording_start_time_ms:
                    start_ms = max(0, int(timestamp_ms - self.recording_start_time_ms))

                # Store in end-of-meeting captions.json archive.
                caption_events.append({
                    "speaker": speaker,
                    "text": text,
                    "offset_ms": start_ms,
                    "timestamp_ms": timestamp_ms,
                })
                print(f"[teams-bot] Caption Event: {speaker} -> {text} (offset: {start_ms}ms)", file=sys.stderr)

                # ── Caption → Track attribution ────────────────────────────────
                # Teams captions already know the speaker name correctly.
                # Find the most recently active Opus track (last 3s) and record
                # the speaker name for it.  This feeds the per-track Whisper
                # pipeline so it labels segments with the real person's name
                # instead of the generic "Speaker" fallback.
                spk_clean = (speaker or "").strip()
                _bot_name = self.bot_display_name.strip().lower()
                if (spk_clean
                        and spk_clean.lower() != _bot_name
                        and spk_clean.lower() not in {"you", "(you)", "speaker"}
                        and len(spk_clean) >= 2):
                    import time as _time
                    _now = _time.time()
                    _cutoff = _now - 3.0  # look back 3 seconds
                    _best_track = None
                    _best_count = 0
                    for _tid, _timestamps in list(track_activity_map.items()):
                        _recent = sum(1 for t in _timestamps if t >= _cutoff)
                        if _recent > _best_count:
                            _best_count = _recent
                            _best_track = _tid
                    if _best_track and _best_count > 0:
                        if track_name_state["map"].get(_best_track) != spk_clean:
                            track_name_state["map"][_best_track] = spk_clean
                            print(
                                f"[teams-bot] Caption attribution: {_best_track} → {spk_clean!r}",
                                file=sys.stderr,
                            )

                # Cancel the previous pending post for this speaker (debounce).
                prev = self._pending_caption_tasks.get(speaker)
                if prev and not prev.done():
                    prev.cancel()

                # Schedule posting 2 s after the last partial update for this speaker.
                async def _debounced(_spk=speaker, _txt=text, _ms=start_ms):
                    await asyncio.sleep(2.0)
                    await _finalize_caption(_spk, _txt, _ms)

                self._pending_caption_tasks[speaker] = asyncio.create_task(_debounced())

            await page.expose_function("zapperTeamsCaptionEvent", _on_caption_event)

            # Optional Microsoft sign-in for org-only meetings.
            if not os.path.exists(session_path):
                signed_in = await self._sign_in_microsoft(page)
                if signed_in:
                    print("[teams-bot] Signed in — joining as authenticated user", file=sys.stderr)
                else:
                    print("[teams-bot] No sign-in — joining as guest", file=sys.stderr)
            else:
                print("[teams-bot] Using saved MS session — skipping sign-in", file=sys.stderr)

            # Use domcontentloaded — Teams web's perpetual signaling never
            # reaches networkidle and would hang Playwright forever.
            await page.goto(self.meeting_url, wait_until="domcontentloaded", timeout=60_000)
            await self._handle_prejoin(page)

            # Start audio capture BEFORE we're admitted so we don't miss
            # the first second of conversation.
            capture = AudioCapture(self.recording_id, self.env)
            output = AudioOutput(self.env)
            await capture.start()
            self.recording_start_time_ms = time.time() * 1000

            await self._join_and_wait_admitted(page)
            await self.api.update_status("recording")

            # Enable live captions and start caption observer
            await self._enable_live_captions(page)
            await self._start_caption_observer(page)

            # live_buf and get_speaker are initialized above before setup_opus_capture
            scraper = ParticipantScraper(page, SEL)
            controller = MeetingController(live_buf, self.recording_id, output, self.api)

            # Background tasks run forever. We foreground-await
            # _watch_for_end so we know when to cancel them. (asyncio.gather
            # would hang — none of the bg tasks return on their own.)
            bg_tasks = [
                asyncio.create_task(capture.stream(self.audio_q)),
                asyncio.create_task(self._fanout_audio()),
                asyncio.create_task(scraper.watch(
                    self._on_scraper_participants  # type: ignore[arg-type]
                )),
                # live_buf.process() (Whisper live path) is gated on LIVE_ENGINE
                # and appended below when enabled. Default "captions" keeps Teams
                # on native captions (more accurate, no Whisper API rate limits).
                asyncio.create_task(controller.run()),
            ]

            # ── Visual capture (non-fatal) ──────────────────────────────────
            _visual_capture = None
            if self.visual_capture_mode and self.visual_capture_mode != "disabled":
                try:
                    from visual_capture import VisualCapture
                    _visual_capture = VisualCapture(
                        recording_id=self.recording_id,
                        out_dir=rec_dir,
                        mode=self.visual_capture_mode,
                        display_num=self.env.display_num,
                        page=page,
                    )
                    bg_tasks.append(asyncio.create_task(_visual_capture.start()))
                    print(
                        f"[teams-bot] Visual capture started: mode={self.visual_capture_mode!r}",
                        file=sys.stderr,
                    )
                except Exception as _vc_exc:
                    print(
                        f"[teams-bot] Visual capture failed to start (non-fatal): {_vc_exc}",
                        file=sys.stderr,
                    )
                    _visual_capture = None
            if _run_whisper:
                if not _live_per_track:
                    bg_tasks.append(asyncio.create_task(live_buf.process(self.live_q)))
                    print(f"[teams-bot] LIVE_ENGINE={_live_engine!r}: Whisper live path ENABLED (mixed buffer)", file=sys.stderr)
                else:
                    # Per-track tasks are created dynamically in _on_pcm_frame as tracks arrive.
                    # dynamic_tasks list is a live reference — we cancel from it at meeting end.
                    print(f"[teams-bot] LIVE_ENGINE={_live_engine!r}: Whisper live path ENABLED (LIVE_PER_TRACK — waiting for first Opus track)", file=sys.stderr)
            else:
                print(f"[teams-bot] LIVE_ENGINE={_live_engine!r}: native captions only", file=sys.stderr)

            try:
                await self._watch_for_end(page)
                print("[teams-bot] Meeting ended — stopping recording", file=sys.stderr)
            except Exception as e:
                print(f"[teams-bot] Watch-for-end exited: {e}", file=sys.stderr)

            for t in bg_tasks:
                t.cancel()
            # Also cancel any per-track Whisper tasks that were created dynamically
            # after the meeting started (dynamic_tasks grows as tracks arrive).
            for t in dynamic_tasks:
                if not t.done():
                    t.cancel()
            await asyncio.gather(*bg_tasks, *dynamic_tasks, return_exceptions=True)

            # Stop visual capture BEFORE finalizing audio (non-fatal).
            if _visual_capture is not None:
                try:
                    await _visual_capture.stop()
                except Exception as _vc_exc:
                    print(
                        f"[teams-bot] Visual capture stop error (non-fatal): {_vc_exc}",
                        file=sys.stderr,
                    )

            wav_path = await capture.stop()

            # Finalize: PulseAudio + per-track Opus → louder wins → audio.wav
            wav_path = finalize_audio(
                capture_wav_path=wav_path,
                rec_dir=rec_dir,
                opus_files=opus_files,
                opus_path_fn=opus_path_fn,
                log_prefix="[teams-bot]",
                track_name_map=track_name_map,
            )

            wav_size = os.path.getsize(wav_path) if os.path.exists(wav_path) else 0
            print(
                f"[teams-bot] Recording saved: {wav_path} ({wav_size/1024/1024:.1f} MB)",
                file=sys.stderr,
            )
            print(f"[teams-bot] Final participants: {self.participants}", file=sys.stderr)
            # Save caption events to captions.json in rec_dir
            try:
                captions_path = os.path.join(rec_dir, "captions.json")
                with open(captions_path, "w") as cf:
                    json.dump(caption_events, cf)
                print(f"[teams-bot] Saved {len(caption_events)} caption events to {captions_path}", file=sys.stderr)
            except Exception as e:
                print(f"[teams-bot] Failed to save captions.json: {e}", file=sys.stderr)

            await self.api.upload_complete(wav_path, self.participants, audio_size_bytes=wav_size)
            await self.api.update_status("processing")
            print("[teams-bot] Pipeline triggered — transcription queued", file=sys.stderr)
            await browser.close()

    # ────────────────────────────────────────────────────────────────────
    # Microsoft sign-in (optional, env-driven)
    # ────────────────────────────────────────────────────────────────────
    async def _sign_in_microsoft(self, page: Page) -> bool:
        """Sign into a Microsoft account so we can join org-only Teams
        meetings. Best-effort; falls back to guest if it fails or the
        env vars are unset.
        """
        email = os.getenv("BOT_MS_EMAIL", "")
        password = os.getenv("BOT_MS_PASSWORD", "")
        if not email or not password:
            print("[teams-bot] No BOT_MS_EMAIL/PASSWORD set — guest mode", file=sys.stderr)
            return False

        try:
            print(f"[teams-bot] Signing in as {email} ...", file=sys.stderr)
            await page.goto(
                "https://login.microsoftonline.com/",
                wait_until="domcontentloaded",
                timeout=30_000,
            )
            await self._screenshot(page, "00a_ms_signin_start")

            # Email
            email_input = page.locator("input[type='email'], input[name='loginfmt']").first
            await email_input.wait_for(state="visible", timeout=15_000)
            await email_input.fill(email)
            await page.keyboard.press("Enter")
            await page.wait_for_timeout(2_000)
            await self._screenshot(page, "00b_ms_after_email")

            # Password
            pwd_input = page.locator("input[type='password'], input[name='passwd']").first
            await pwd_input.wait_for(state="visible", timeout=15_000)
            await pwd_input.fill(password)
            await page.keyboard.press("Enter")
            await page.wait_for_timeout(3_000)
            await self._screenshot(page, "00c_ms_after_password")

            # MFA / approval window — wait up to 90s for the user
            # to complete it on their phone.
            print("[teams-bot] Waiting for sign-in to settle (approve MFA if shown)...", file=sys.stderr)
            deadline = time.time() + 90
            signed_in = False
            while time.time() < deadline:
                u = page.url
                if "login.microsoftonline.com" not in u and "login.live.com" not in u:
                    signed_in = True
                    break
                await page.wait_for_timeout(2_000)

            await self._screenshot(page, "00d_ms_final_signin")

            if not signed_in:
                print("[teams-bot] MS sign-in timed out", file=sys.stderr)
                return False

            # "Stay signed in?" prompt — Microsoft uses either a real
            # <button> or an <input type="submit" value="Yes">.
            for sel in [
                "input[type='submit'][value='Yes']",
                "input[type='submit'][value='No']",
                "button[data-report-event='Signin_Submit']",
            ]:
                try:
                    el = page.locator(sel).first
                    if await el.is_visible(timeout=2_000):
                        await el.click()
                        await page.wait_for_timeout(1_500)
                        break
                except (PWTimeout, Exception):
                    pass
            for label in ["Yes", "No", "Continue"]:
                try:
                    btn = page.get_by_role("button", name=label)
                    if await btn.is_visible(timeout=2_000):
                        await btn.click()
                        await page.wait_for_timeout(1_500)
                        break
                except (PWTimeout, Exception):
                    pass

            # Persist session
            session_path = os.getenv("BOT_MS_SESSION_PATH", "/data/recordings/ms_session.json")
            try:
                os.makedirs(os.path.dirname(session_path), exist_ok=True)
                await page.context.storage_state(path=session_path)
                print(f"[teams-bot] Session saved to {session_path}", file=sys.stderr)
            except Exception as exc:
                print(f"[teams-bot] Could not save session: {exc}", file=sys.stderr)

            return True

        except Exception as exc:
            print(f"[teams-bot] MS sign-in error: {exc}", file=sys.stderr)
            await self._screenshot(page, "00e_ms_signin_exception")
            return False

    # ────────────────────────────────────────────────────────────────────
    # Pre-join handling
    # ────────────────────────────────────────────────────────────────────
    async def _screenshot(self, page: Page, name: str):
        try:
            path = f"/tmp/zapper_teams_{name}.png"
            await page.screenshot(path=path)
            print(f"[teams-bot] Screenshot saved: {path}", file=sys.stderr)
        except Exception as exc:
            print(f"[teams-bot] Screenshot failed ({name}): {exc}", file=sys.stderr)

    async def _handle_prejoin(self, page: Page):
        """Teams pre-join flow:
        - Dismiss "Open in Teams app?" prompt → "Continue on this browser"
        - Fill display name (guest path)
        - Mute mic + turn off camera
        - (Join is clicked separately in _join_and_wait_admitted)
        """
        print(f"[teams-bot] Navigated to: {page.url}", file=sys.stderr)
        await page.wait_for_timeout(3_000)
        await self._screenshot(page, "01_after_nav")

        # Step 1: dismiss the "open in app" prompt — try multiple wordings.
        for label in [
            "Continue on this browser",
            "Continue in this browser",
            "Use the web app instead",
            "Join on the web instead",
        ]:
            try:
                btn = page.get_by_role("button", name=label)
                if await btn.is_visible(timeout=3_000):
                    print(f"[teams-bot] Clicking: {label}", file=sys.stderr)
                    await btn.click()
                    await page.wait_for_timeout(1_500)
                    break
            except (PWTimeout, Exception):
                continue
        await self._screenshot(page, "02_after_browser_choice")

        # Step 2: wait for the pre-join screen.
        # The full Teams web app uses [data-tid='prejoin-screen'], but the
        # Teams *light experience* (teams.live.com) does NOT have that element.
        # Instead wait for the name input or Join button to appear.
        prejoined = False
        for wait_sel in [
            SEL.get("prejoin_screen", None),
            "input[placeholder*='name' i]",
            "input[aria-label*='name' i]",
            "[data-tid='prejoin-display-name-input']",
            "button:has-text('Join now')",
            "button:has-text('Join')",
        ]:
            if not wait_sel:
                continue
            try:
                await page.wait_for_selector(wait_sel, timeout=30_000)
                print(f"[teams-bot] Pre-join screen ready ({wait_sel})", file=sys.stderr)
                prejoined = True
                break
            except PWTimeout:
                continue
        if not prejoined:
            print("[teams-bot] Pre-join selector not found — proceeding anyway", file=sys.stderr)
        await self._screenshot(page, "03_prejoin")

        # Step 3: fill display name using JavaScript so the tooltip overlay
        # cannot intercept the value.  The React input value setter trick works
        # because it bypasses React's synthetic-event proxy while still
        # triggering the Input/Change events that React listens to.
        js_filled = False
        try:
            js_filled = await page.evaluate("""
                (name) => {
                    const inputs = [...document.querySelectorAll('input')];
                    const nameInput = inputs.find(i =>
                        (i.placeholder || '').toLowerCase().includes('name') ||
                        (i.getAttribute('aria-label') || '').toLowerCase().includes('name') ||
                        i.getAttribute('data-tid') === 'prejoin-display-name-input'
                    );
                    if (!nameInput) return false;
                    // React-compatible value setter.
                    try {
                        const setter = Object.getOwnPropertyDescriptor(
                            window.HTMLInputElement.prototype, 'value'
                        ).set;
                        setter.call(nameInput, name);
                    } catch (_) {
                        nameInput.value = name;
                    }
                    nameInput.dispatchEvent(new Event('input',  { bubbles: true }));
                    nameInput.dispatchEvent(new Event('change', { bubbles: true }));
                    nameInput.dispatchEvent(new KeyboardEvent('keyup', { bubbles: true }));
                    return nameInput.value;
                }
            """, BOT_DISPLAY_NAME)
            if js_filled:
                print(f"[teams-bot] Name set via JS: {js_filled!r}", file=sys.stderr)
            else:
                print("[teams-bot] JS name fill returned falsy — falling back to keyboard", file=sys.stderr)
        except Exception as exc:
            print(f"[teams-bot] JS name fill error: {exc}", file=sys.stderr)

        if not js_filled:
            # Keyboard fallback: escape tooltip, click field, type.
            try:
                await page.keyboard.press("Escape")
                await page.wait_for_timeout(300)
            except Exception:
                pass
            try:
                for sel in [
                    SEL.get("name_input"),
                    "input[data-tid='prejoin-display-name-input']",
                    "input[placeholder*='name' i]",
                    "input[aria-label*='name' i]",
                ]:
                    if not sel:
                        continue
                    try:
                        name_input = page.locator(sel).first
                        if await name_input.is_visible(timeout=2_000):
                            print(f"[teams-bot] Keyboard name fill via {sel}", file=sys.stderr)
                            try:
                                await page.click("body", position={"x": 50, "y": 50})
                                await page.wait_for_timeout(300)
                            except Exception:
                                pass
                            await name_input.click()
                            await page.wait_for_timeout(300)
                            await name_input.click(click_count=3)  # select all then overwrite
                            await page.wait_for_timeout(100)
                            await name_input.fill("")
                            await name_input.type(BOT_DISPLAY_NAME, delay=30)
                            await page.wait_for_timeout(300)
                            filled = await name_input.input_value()
                            print(f"[teams-bot] Keyboard fill result: {filled!r}", file=sys.stderr)
                            break
                    except (PWTimeout, Exception) as exc:
                        print(f"[teams-bot] Keyboard fill via {sel} failed: {exc}", file=sys.stderr)
                        continue
            except Exception as exc:
                print(f"[teams-bot] Name fill fallback failed: {exc}", file=sys.stderr)
        await self._screenshot(page, "04_after_name")

        # Step 4: mute the mic so the bot doesn't echo anything back into
        # the meeting. Toggle button cycles: try every label variant.
        await self._toggle_off(page, [
            SEL.get("toggle_mic"),
            "[data-tid='toggle-mute']",
            "button[aria-label*='Mute' i]",
            "button[aria-label*='microphone' i]",
        ], desired_state="muted", labels_off=["Unmute", "Microphone is off"])

        # Step 5: turn off camera.
        await self._toggle_off(page, [
            SEL.get("toggle_camera"),
            "[data-tid='toggle-video']",
            "button[aria-label*='camera' i]",
            "button[aria-label*='video' i]",
        ], desired_state="off", labels_off=["Turn camera on", "Camera is off"])

        await self._screenshot(page, "05_after_av_toggle")

    async def _toggle_off(self, page: Page, selectors: list, desired_state: str, labels_off: list):
        """Click a toggle once; if its current accessible-name matches one
        of `labels_off`, leave it. Best-effort and logs what it tried.
        """
        for sel in selectors:
            if not sel:
                continue
            try:
                btn = page.locator(sel).first
                if not await btn.is_visible(timeout=1_500):
                    continue
                aria = (await btn.get_attribute("aria-label")) or ""
                if any(lbl.lower() in aria.lower() for lbl in labels_off):
                    print(f"[teams-bot] Already {desired_state} ({aria!r}) — skip {sel}", file=sys.stderr)
                    return
                print(f"[teams-bot] Toggling {desired_state}: {sel} (aria={aria!r})", file=sys.stderr)
                await btn.click()
                await page.wait_for_timeout(400)
                return
            except (PWTimeout, Exception):
                continue
        print(f"[teams-bot] No selector matched for {desired_state} toggle", file=sys.stderr)

    # ────────────────────────────────────────────────────────────────────
    # Join + admission detection (mirrors meet_bot._wait_admitted)
    # ────────────────────────────────────────────────────────────────────
    async def _join_and_wait_admitted(self, page: Page):
        # Click the Join button — try data-tid then text variants.
        joined = False
        for sel in [
            SEL.get("join_button", "[data-tid='prejoin-join-button']"),
            "[data-tid='prejoin-join-button']",
            "button:has-text('Join now')",
            "button:has-text('Join meeting')",
            "button:has-text('Join')",
        ]:
            try:
                btn = page.locator(sel).first
                await btn.wait_for(state="visible", timeout=10_000)
                print(f"[teams-bot] Clicking join button: {sel}", file=sys.stderr)
                await btn.click(force=True)
                joined = True
                break
            except (PWTimeout, Exception) as exc:
                print(f"[teams-bot] Join not found via {sel}: {exc}", file=sys.stderr)
                continue
        await self._screenshot(page, "06_after_join_click")
        await page.wait_for_timeout(3_000)  # give Teams time to process the join click

        if not joined:
            await self._screenshot(page, "06b_join_failed")
            raise RuntimeError("Teams join button never found")

        # If the pre-join screen is STILL visible after clicking Join, it means the
        # name was empty (Teams won't proceed without a name).  Retry name fill once.
        try:
            still_prejoin = False
            for sel in [
                "input[placeholder*='name' i]",
                "input[data-tid='prejoin-display-name-input']",
                "input[aria-label*='name' i]",
            ]:
                try:
                    loc = page.locator(sel).first
                    if await loc.is_visible(timeout=1_500):
                        still_prejoin = True
                        print(f"[teams-bot] Pre-join still visible after join click — retrying name fill via {sel}", file=sys.stderr)
                        await loc.click()
                        await page.wait_for_timeout(200)
                        await loc.click(click_count=3)  # select all then overwrite
                        await loc.fill("")
                        await loc.type(BOT_DISPLAY_NAME, delay=30)
                        await page.wait_for_timeout(500)
                        break
                except Exception:
                    continue

            if still_prejoin:
                await self._screenshot(page, "06c_name_retry")
                # Click Join again after filling the name.
                for sel in [
                    "[data-tid='prejoin-join-button']",
                    "button:has-text('Join now')",
                    "button:has-text('Join')",
                ]:
                    try:
                        btn = page.locator(sel).first
                        if await btn.is_visible(timeout=3_000):
                            print(f"[teams-bot] Re-clicking join after name retry: {sel}", file=sys.stderr)
                            await btn.click(force=True)
                            await page.wait_for_timeout(3_000)
                            break
                    except Exception:
                        continue
                await self._screenshot(page, "06d_after_retry_join")
        except Exception as exc:
            print(f"[teams-bot] Pre-join retry failed: {exc}", file=sys.stderr)

        # Now poll for admission with multiple strategies.
        await self.api.update_status("lobby")
        deadline = time.time() + self.lobby_timeout
        poll = 0
        while time.time() < deadline:
            poll += 1

            # 1. data-tid hangup button — the canonical in-meeting marker.
            for sel in [
                SEL.get("in_meeting_indicator", "[data-tid='hangup-button']"),
                "[data-tid='hangup-button']",
                "[data-tid='call-end']",
            ]:
                try:
                    if await page.locator(sel).first.is_visible(timeout=1_500):
                        print(f"[teams-bot] Admitted — {sel} visible", file=sys.stderr)
                        return
                except Exception:
                    pass

            # 2. Accessible-name buttons that only appear in-meeting.
            for label in ["Leave", "Hang up", "Leave meeting", "End call"]:
                try:
                    btn = page.get_by_role("button", name=label)
                    if await btn.is_visible(timeout=1_000):
                        print(f"[teams-bot] Admitted — button '{label}' visible", file=sys.stderr)
                        return
                except Exception:
                    pass

            # 3. CSS variants for the leave/hangup control.
            for sel in [
                "button[aria-label*='Leave' i]",
                "button[aria-label*='Hang up' i]",
                "button[data-tid*='leave']",
                "[role='button'][aria-label*='leave' i]",
            ]:
                try:
                    if await page.locator(sel).first.is_visible(timeout=800):
                        print(f"[teams-bot] Admitted — CSS hit {sel}", file=sys.stderr)
                        return
                except Exception:
                    pass

            # 4. URL heuristic — Teams transitions out of /prejoin into
            #    /meet or /modern* once admitted.
            url = page.url
            if "/prejoin" not in url and "teams" in url and "/meetup-join" not in url and "launch" not in url and "launcher" not in url:
                # Sanity-check: not on an error page.
                if "blocked" not in url and "lobby" not in url:
                    print(f"[teams-bot] Admitted — URL heuristic: {url}", file=sys.stderr)
                    return

            # 5. The Join button disappeared (clicked = transitioned).
            try:
                join = page.get_by_role("button", name="Join now")
                still_pre = await join.is_visible(timeout=800)
                if not still_pre:
                    # Combine with hangup absence to avoid false positive
                    # while transitioning through lobby.
                    pass
            except Exception:
                pass

            # 6. JS-eval: any button looking like a meeting control?
            try:
                in_call = await page.evaluate("""
                    () => {
                        const btns = [...document.querySelectorAll('button,[role="button"]')];
                        const has = (re) => btns.some(b => re.test(
                            (b.getAttribute('aria-label') || '') + ' ' +
                            (b.getAttribute('data-tid')   || '') + ' ' +
                            (b.textContent                || '')
                        ));
                        return has(/leave|hang ?up|end call/i)
                            && !has(/^Join now$/i);
                    }
                """)
                if in_call:
                    print("[teams-bot] Admitted — JS in-call check passed", file=sys.stderr)
                    return
            except Exception:
                pass

            if poll % 5 == 0:
                await self._screenshot(page, f"lobby_{poll:03d}")
                print(
                    f"[teams-bot] Still waiting for admission... "
                    f"{int(deadline - time.time())}s left | URL={page.url}",
                    file=sys.stderr,
                )

            await asyncio.sleep(3)

        await self._screenshot(page, "lobby_timeout")
        await self.api.update_status("lobby_timeout")
        raise RuntimeError(f"Bot never admitted to Teams within {self.lobby_timeout}s")

    # ────────────────────────────────────────────────────────────────────
    # Meeting end detection (mirrors meet_bot._watch_for_end)
    # ────────────────────────────────────────────────────────────────────
    async def _watch_for_end(self, page: Page):
        end_texts = [
            "Meeting ended",
            "The meeting has ended",
            "You left the meeting",
            "You've left the meeting",
            "Call ended",
            "You left the call",
            "You've been removed from the meeting",
            "You've been removed from the call",
            "You have been removed",
            "You've been removed",
            "You were removed",
        ]
        alone_since: float | None = None
        max_count_seen = 0
        admitted_at = time.time()
        roster_opened = False
        poll = 0

        while True:
            await asyncio.sleep(8)
            poll += 1
            if page.is_closed():
                print("[teams-bot] Page closed — meeting ended", file=sys.stderr)
                return

            # Check if user clicked "Stop" in the dashboard
            if await self.api.is_cancelled():
                print("[teams-bot] Cancelled from dashboard — stopping recording", file=sys.stderr)
                return

            # Open the roster panel once shortly after admission so that
            # participant names appear in the DOM.
            if not roster_opened and poll >= 1:
                opened = False
                for sel in [
                    SEL.get("roster_button", "[data-tid='roster-button']"),
                    "[data-tid='roster-button']",
                    "[data-tid='show-participants']",
                    "button[aria-label*='people' i]",
                    "button[aria-label*='participant' i]",
                ]:
                    if not sel:
                        continue
                    try:
                        btn = page.locator(sel).first
                        if await btn.is_visible(timeout=1_500):
                            await btn.click(timeout=2_000)
                            opened = True
                            print(f"[teams-bot] Roster opened via {sel}", file=sys.stderr)
                            break
                    except Exception:
                        continue
                if not opened:
                    # Keyboard shortcut: Ctrl+Shift+P toggles people pane.
                    try:
                        await page.keyboard.press("Control+Shift+KeyP")
                        opened = True
                        print("[teams-bot] Roster opened via keyboard shortcut", file=sys.stderr)
                    except Exception as exc:
                        print(f"[teams-bot] Roster keyboard shortcut failed: {exc}", file=sys.stderr)
                roster_opened = True
                await asyncio.sleep(1.5)

            try:
                # 1. End-of-meeting text on screen.
                for txt in end_texts:
                    try:
                        if await page.get_by_text(txt, exact=False).is_visible(timeout=400):
                            print(f"[teams-bot] Detected end text: '{txt}'", file=sys.stderr)
                            return
                    except Exception:
                        pass

                # 2. Navigated away from the Teams meeting page.
                url = page.url
                if "teams." not in url or "blank" in url or "/bye" in url.lower() or "/left" in url.lower():
                    print(f"[teams-bot] Navigated away: {url}", file=sys.stderr)
                    return

                # 4. Participant count + name extraction (DOM-based with
                #    multiple Teams roster strategies).
                info = await page.evaluate("""
                    () => {
                        const out = { count: -1, names: [], self: '' };
                        // Roster row strategies (Teams uses several variants).
                        const rows = [
                            ...document.querySelectorAll('[data-tid="roster-participant"]'),
                            ...document.querySelectorAll('[data-tid="participantsList-row"]'),
                            ...document.querySelectorAll('[role="treeitem"]'),
                            ...document.querySelectorAll('li[data-tid*="participant"]'),
                        ];
                        const names = new Set();
                        let selfName = '';
                        const clean = (s) => (s || '')
                            .replace(/\\s+/g, ' ')
                            .replace(/\\(You\\)/i, '')
                            .replace(/\\(Guest\\)/i, '')
                            .replace(/Organizer/gi, '')
                            .replace(/Muted|Unmuted|Camera (on|off)/gi, '')
                            .trim();
                        for (const row of rows) {
                            const isSelf = /\\(You\\)/i.test(row.textContent || '');
                            // Prefer the explicit display-name child.
                            let n = '';
                            const dn = row.querySelector('[data-tid="participant-display-name"], [data-tid*="display-name"]');
                            if (dn) n = clean(dn.textContent);
                            if (!n) {
                                const al = row.getAttribute('aria-label');
                                if (al) n = clean(al.split(',')[0]);
                            }
                            if (!n) n = clean(row.textContent);
                            if (!n || n.length < 2 || n.length > 80) continue;
                            if (isSelf) selfName = n;
                            else names.add(n);
                        }
                        // Count from video/audio tile elements as a backup.
                        const tiles = document.querySelectorAll('[data-tid="participant-tile"], [data-cid*="participant"]');
                        out.count = tiles.length || rows.length || -1;
                        out.names = [...names];
                        out.self = selfName;
                        return out;
                    }
                """)
                participant_count = info.get("count", -1) if isinstance(info, dict) else -1
                names = info.get("names", []) if isinstance(info, dict) else []
                self_name = (info.get("self") or "").strip() if isinstance(info, dict) else ""
                if participant_count > 0:
                    max_count_seen = max(max_count_seen, participant_count)

                bot_env_name = self.bot_display_name.strip().lower()
                self_lower = self_name.lower()
                for n in names:
                    n_clean = n.strip()
                    if not n_clean:
                        continue
                    nl = n_clean.lower()
                    if nl == bot_env_name or (self_lower and nl == self_lower):
                        continue
                    if nl in {"you", "(you)"}:
                        continue
                    if n_clean not in self._participants_seen:
                        self._participants_seen.add(n_clean)
                        self.participants.append(n_clean)
                        print(f"[teams-bot] Participant detected: {n_clean}", file=sys.stderr)
                        await self.api.update_participants(self.participants)

                # Alone-after-peak detection (gated by auto_leave_when_alone and min_meeting_seconds)
                now = time.time()
                in_meeting_for = now - admitted_at
                if self.auto_leave_when_alone and in_meeting_for >= self.min_meeting_seconds:
                    is_alone = (participant_count != -1 and participant_count <= 1)
                    if is_alone:
                        if alone_since is None:
                            alone_since = now
                            print(
                                f"[teams-bot] Count dropped ({participant_count}/{max_count_seen} peak), "
                                f"waiting {self.max_alone_seconds}s...",
                                file=sys.stderr,
                            )
                        elif now - alone_since >= self.max_alone_seconds:
                            print(
                                f"[teams-bot] Bot alone for {self.max_alone_seconds}s — meeting ended",
                                file=sys.stderr,
                            )
                            return
                    else:
                        if alone_since is not None:
                            print(
                                f"[teams-bot] Count recovered ({participant_count}), "
                                f"resetting alone timer",
                                file=sys.stderr,
                            )
                        alone_since = None
                else:
                    alone_since = None

                if poll % 4 == 0:
                    print(
                        f"[teams-bot] In meeting... poll={poll} count={participant_count} "
                        f"peak={max_count_seen} in_meeting={int(in_meeting_for)}s url={page.url}",
                        file=sys.stderr,
                    )
            except Exception as exc:
                print(f"[teams-bot] watch_for_end error: {exc}", file=sys.stderr)



    # ────────────────────────────────────────────────────────────────────
    # Live Caption Observation & Click Helpers
    # ────────────────────────────────────────────────────────────────────
    async def _enable_live_captions(self, page: Page):
        print("[teams-bot] [Captions] Attempting to enable Teams live captions...", file=sys.stderr)
        await page.wait_for_timeout(3000)

        already_enabled = await page.evaluate("""
            () => {
                return !!document.querySelector('[data-tid="closed-caption-renderer-wrapper"]');
            }
        """)
        if already_enabled:
            print("[teams-bot] [Captions] Live captions already enabled", file=sys.stderr)
            return

        try:
            more_button = page.locator(
                '#callingButtons-showMoreBtn, button[aria-label="More"], button[aria-label="More options"]'
            ).first
            await more_button.click(timeout=8000)
            print("[teams-bot] [Captions] Clicked More menu", file=sys.stderr)
            await page.wait_for_timeout(1000)

            enable_result = await page.evaluate("""
                () => {
                    const getVisibleItems = () => {
                        const items = document.querySelectorAll('[role="menuitem"], [role="menuitemcheckbox"], [role="menuitemradio"]');
                        return Array.from(items).filter(el => el.offsetParent !== null);
                    };

                    const items = getVisibleItems();
                    const texts = items.map(el => (el.textContent || '').trim().toLowerCase());

                    // Path A (guest): Direct "Captions" menu item
                    for (const el of items) {
                        const text = (el.textContent || '').trim().toLowerCase();
                        if (text === 'captions' || text === 'show live captions' || text === 'turn on live captions') {
                            el.click();
                            return { clicked: (el.textContent || '').trim(), path: 'direct' };
                        }
                    }

                    // Path B (host): "Language and speech" submenu
                    for (const el of items) {
                        const text = (el.textContent || '').toLowerCase();
                        if (text.includes('language') && text.includes('speech')) {
                            el.click();
                            return { clicked: (el.textContent || '').trim(), path: 'submenu' };
                        }
                    }

                    return { clicked: null, path: 'none', available: texts.join(' | ') };
                }
            """)

            if not enable_result or not enable_result.get("clicked"):
                raise RuntimeError(f"Could not find captions menu item. Available: {enable_result.get('available') if enable_result else 'None'}")

            print(f"[teams-bot] [Captions] Clicked: \"{enable_result.get('clicked')}\" ({enable_result.get('path')})", file=sys.stderr)
            await page.wait_for_timeout(1000)

            if enable_result.get("path") == "submenu":
                clicked_sub = await page.evaluate("""
                    () => {
                        const items = document.querySelectorAll('[role="menuitem"], [role="menuitemcheckbox"], [role="menuitemradio"]');
                        for (const el of items) {
                            const text = (el.textContent || '').toLowerCase();
                            if (text.includes('live captions') && el.offsetParent) {
                                el.click();
                                return (el.textContent || '').trim();
                            }
                        }
                        return null;
                    }
                """)
                if clicked_sub:
                    print(f"[teams-bot] [Captions] Clicked submenu: \"{clicked_sub}\"", file=sys.stderr)
                else:
                    print("[teams-bot] [Captions] ⚠️ Could not find live captions in submenu", file=sys.stderr)
                await page.wait_for_timeout(1500)

            captions_enabled = await page.evaluate("""
                () => {
                    return !!document.querySelector('[data-tid="closed-caption-renderer-wrapper"]');
                }
            """)
            if captions_enabled:
                print("[teams-bot] [Captions] ✅ Live captions enabled successfully", file=sys.stderr)
            else:
                print("[teams-bot] [Captions] ⚠️ Captions menu clicked but wrapper not found yet — caption observer will detect when it appears", file=sys.stderr)

        except Exception as e:
            print(f"[teams-bot] [Captions] Error enabling live captions: {e}", file=sys.stderr)
            try:
                await page.keyboard.press("Escape")
            except Exception:
                pass

    async def _start_caption_observer(self, page: Page):
        await page.evaluate(f"window._zapperBotName = {json.dumps(BOT_DISPLAY_NAME)}")

        await page.evaluate("""
            () => {
                if (window._zapperCaptionObserverInitialized) {
                    console.log("[zapper] Caption observer already initialized");
                    return;
                }
                window._zapperCaptionObserverInitialized = true;
                console.log("[zapper] Initializing caption observer...");

                // Per-speaker last-seen text — avoids re-emitting the same
                // in-progress caption segment while Teams is still building it.
                const lastTextBySpeaker = {};
                // Finalised keys (speaker::text) we have already emitted so
                // a caption line that has scrolled off cannot be re-emitted.
                const emittedKeys = new Set();

                const botNameLower = (window._zapperBotName || "Zapper Recorder").toLowerCase();

                const processCaptions = () => {
                    const wrapper = document.querySelector('[data-tid="closed-caption-renderer-wrapper"]');
                    if (!wrapper) return;

                    // Teams renders each caption "bubble" as a separate
                    // container. Collect ALL of them, not just the last.
                    // Strategy: pair every [data-tid="author"] with the
                    // nearest following [data-tid="closed-caption-text"].
                    const captionItems = [];

                    // Try the structured row approach first (most Teams versions).
                    const rows = wrapper.querySelectorAll(
                        '[data-tid="closed-caption-row"], .closed-caption-row, ' +
                        '[class*="captionRow"], [class*="caption-row"]'
                    );
                    if (rows.length > 0) {
                        for (const row of rows) {
                            const authorEl = row.querySelector(
                                '[data-tid="author"], [class*="author"]'
                            );
                            const textEl = row.querySelector(
                                '[data-tid="closed-caption-text"], [class*="captionText"], [class*="caption-text"]'
                            );
                            if (!authorEl || !textEl) continue;
                            const speaker = (authorEl.textContent || '').trim();
                            const text    = (textEl.textContent   || '').trim();
                            if (speaker && text) captionItems.push({ speaker, text });
                        }
                    }

                    // Fallback: pair author/text elements by DOM order.
                    if (captionItems.length === 0) {
                        const authorEls = [...wrapper.querySelectorAll('[data-tid="author"]')];
                        const textEls   = [...wrapper.querySelectorAll('[data-tid="closed-caption-text"]')];
                        const n = Math.min(authorEls.length, textEls.length);
                        for (let i = 0; i < n; i++) {
                            const speaker = (authorEls[i].textContent || '').trim();
                            const text    = (textEls[i].textContent   || '').trim();
                            if (speaker && text) captionItems.push({ speaker, text });
                        }
                    }

                    const now = Date.now();
                    for (const { speaker, text } of captionItems) {
                        // Normalise the speaker name:
                        // Teams shows the local user as "Name (You)" — strip
                        // "(You)" so we record the real name for the host too.
                        const cleanSpeaker = speaker.replace(/\\s*\\(You\\)\\s*/i, '').trim() || speaker.trim();

                        // Skip the bot itself.
                        const speakerLower = cleanSpeaker.toLowerCase();
                        if (speakerLower.includes(botNameLower) || speakerLower.includes('zapper')) continue;

                        // Deduplicate: only emit when the text for this speaker
                        // has actually changed (Teams streams partial captions).
                        if (lastTextBySpeaker[cleanSpeaker] === text) continue;
                        lastTextBySpeaker[cleanSpeaker] = text;

                        const key = cleanSpeaker + '::' + text;
                        if (emittedKeys.has(key)) continue;
                        emittedKeys.add(key);
                        // Prevent the set growing unboundedly.
                        if (emittedKeys.size > 2000) {
                            const oldest = emittedKeys.values().next().value;
                            emittedKeys.delete(oldest);
                        }

                        console.log('[zapper] Caption: ' + cleanSpeaker + ' \u2192 ' + text.substring(0, 60));
                        if (typeof window.zapperTeamsCaptionEvent === 'function') {
                            window.zapperTeamsCaptionEvent(cleanSpeaker, text, now);
                        }
                    }
                };

                let captionsEnabled = false;
                const startCaptionObserver = () => {
                    const wrapper = document.querySelector('[data-tid="closed-caption-renderer-wrapper"]');
                    if (!wrapper) return false;
                    captionsEnabled = true;
                    console.log("[zapper] Caption wrapper found — starting mutation observer");
                    const observer = new MutationObserver(processCaptions);
                    observer.observe(wrapper, { childList: true, subtree: true, characterData: true });
                    processCaptions();
                    setInterval(processCaptions, 500);
                    return true;
                };

                const detectionInterval = setInterval(() => {
                    if (startCaptionObserver()) {
                        clearInterval(detectionInterval);
                    }
                }, 2000);

                const bodyObserver = new MutationObserver(() => {
                    if (!captionsEnabled && startCaptionObserver()) {
                        bodyObserver.disconnect();
                        clearInterval(detectionInterval);
                    }
                });
                bodyObserver.observe(document.body, { childList: true, subtree: true });
            }
        """)
