"""
VisualCapture — manages screen capture during a live meeting bot session.

Modes
-----
screenshot_Ns : Playwright page.screenshot() saved as JPEG every N seconds to
                /data/recordings/{id}/screenshots/{timestamp_ms}.jpg

video         : ffmpeg x11grab on the Xvfb virtual display → H.264 screen.mp4
                saved at /data/recordings/{id}/screen.mp4

Design principles
-----------------
* Completely non-fatal: if ffmpeg fails to launch, or a screenshot call
  throws, we log and continue — the audio recording MUST NOT be affected.
* Self-contained: no new Docker dependencies. ffmpeg and xvfb are already
  installed by the bot-runner Dockerfile.
* After stop(), video mode notifies the backend via POST /video-ready so
  the database knows where the mp4 lives.
"""

import asyncio
import os
import subprocess
import sys
import time
from typing import Optional

import httpx

BACKEND_URL = os.getenv("BACKEND_URL", "http://backend:8000")

VALID_MODES = frozenset({
    "screenshot_1s",
    "screenshot_2s",
    "screenshot_5s",
    "screenshot_10s",
    "video",
})


class VisualCapture:
    """
    Starts and stops visual capture for one bot session.

    Parameters
    ----------
    recording_id : str
        UUID of the recording row.
    out_dir : str
        Absolute path to the recording directory
        (e.g. /data/recordings/{recording_id}).
    mode : str
        One of the VALID_MODES values, or 'disabled'.
    display_num : int
        Xvfb display number used by this bot slot (e.g. 99 for slot 0).
    page : playwright.async_api.Page
        The live Playwright page to screenshot (screenshot mode only).
    """

    def __init__(
        self,
        recording_id: str,
        out_dir: str,
        mode: str,
        display_num: int,
        page,
    ):
        self.recording_id = recording_id
        self.out_dir = out_dir
        self.mode = mode
        self.display_num = display_num
        self.page = page
        self._stop_event: asyncio.Event = asyncio.Event()
        self._ffmpeg_proc: Optional[subprocess.Popen] = None
        self._video_path: Optional[str] = None
        self._tmp_path: Optional[str] = None  # raw capture before faststart remux

    # ── Public API ─────────────────────────────────────────────────────────

    async def start(self) -> None:
        """Start capture. Returns immediately for video mode (ffmpeg runs as
        a subprocess). Runs until _stop_event is set for screenshot mode."""
        if self.mode not in VALID_MODES:
            print(
                f"[visual_capture] mode={self.mode!r} not in VALID_MODES — skipping",
                file=sys.stderr,
            )
            return

        if self.mode.startswith("screenshot_"):
            interval = self._parse_interval(self.mode)
            await self._screenshot_loop(interval)
        elif self.mode == "video":
            self._start_ffmpeg()
            # Keep this coroutine alive so the caller can cancel it cleanly.
            # It does nothing — ffmpeg runs in its own subprocess.
            while not self._stop_event.is_set():
                await asyncio.sleep(5)

    async def stop(self) -> None:
        """Signal capture to stop. For video mode, waits for ffmpeg to flush
        the mp4, runs a faststart remux pass, then calls /video-ready."""
        self._stop_event.set()

        if self._ffmpeg_proc is not None:
            try:
                self._ffmpeg_proc.terminate()
                # Give ffmpeg up to 8 seconds to flush and finalize the mp4.
                for _ in range(16):
                    if self._ffmpeg_proc.poll() is not None:
                        break
                    await asyncio.sleep(0.5)
                if self._ffmpeg_proc.poll() is None:
                    # Still running — kill hard
                    self._ffmpeg_proc.kill()
                    await asyncio.sleep(1)
            except Exception as exc:
                print(
                    f"[visual_capture] error stopping ffmpeg: {exc}",
                    file=sys.stderr,
                )

            # Remux with -movflags +faststart so the browser can seek and
            # start playback without downloading the full file first.
            # The live x11grab capture writes the moov atom at the end of
            # the file; the remux pass moves it to the start.
            if self._tmp_path and self._video_path and os.path.isfile(self._tmp_path):
                print(
                    "[visual_capture] remuxing with faststart …",
                    file=sys.stderr,
                )
                remux_ok = await self._remux_faststart(self._tmp_path, self._video_path)
                if remux_ok:
                    try:
                        os.unlink(self._tmp_path)
                    except OSError:
                        pass
                else:
                    # Remux failed — fall back to the raw tmp file
                    print(
                        "[visual_capture] faststart remux failed; using raw capture",
                        file=sys.stderr,
                    )
                    try:
                        os.rename(self._tmp_path, self._video_path)
                    except OSError as exc:
                        print(
                            f"[visual_capture] rename fallback also failed: {exc}",
                            file=sys.stderr,
                        )

            # Notify the backend that the mp4 is ready.
            if self._video_path and os.path.isfile(self._video_path):
                video_size_mb = os.path.getsize(self._video_path) / 1024 / 1024
                print(
                    f"[visual_capture] video saved: {self._video_path} "
                    f"({video_size_mb:.1f} MB)",
                    file=sys.stderr,
                )
                await self._notify_backend(self._video_path)
            else:
                print(
                    "[visual_capture] video file missing after ffmpeg stop "
                    f"(path={self._video_path!r})",
                    file=sys.stderr,
                )

    # ── Internal helpers ───────────────────────────────────────────────────

    @staticmethod
    def _parse_interval(mode: str) -> int:
        """Extract seconds from mode name, e.g. 'screenshot_5s' → 5."""
        try:
            return int(mode.split("_")[1].rstrip("s"))
        except (IndexError, ValueError):
            return 10  # safe fallback

    async def _screenshot_loop(self, interval_seconds: int) -> None:
        """Take a JPEG screenshot every interval_seconds until stop() is called."""
        screenshots_dir = os.path.join(self.out_dir, "screenshots")
        try:
            os.makedirs(screenshots_dir, exist_ok=True)
        except OSError as exc:
            print(
                f"[visual_capture] failed to create screenshots dir: {exc}",
                file=sys.stderr,
            )
            return

        print(
            f"[visual_capture] screenshot mode started (every {interval_seconds}s) "
            f"→ {screenshots_dir}",
            file=sys.stderr,
        )
        count = 0
        while not self._stop_event.is_set():
            try:
                ts = int(time.time() * 1000)
                img: bytes = await self.page.screenshot(
                    type="jpeg",
                    quality=60,
                )
                path = os.path.join(screenshots_dir, f"{ts}.jpg")
                with open(path, "wb") as fh:
                    fh.write(img)
                count += 1
                if count % 10 == 0:
                    print(
                        f"[visual_capture] {count} screenshots saved",
                        file=sys.stderr,
                    )
            except asyncio.CancelledError:
                break
            except Exception as exc:
                print(
                    f"[visual_capture] screenshot failed: {exc}",
                    file=sys.stderr,
                )
            try:
                await asyncio.wait_for(
                    asyncio.shield(self._stop_event.wait()),
                    timeout=interval_seconds,
                )
                # _stop_event was set → exit cleanly
                break
            except asyncio.TimeoutError:
                pass  # interval elapsed, take next screenshot

        print(
            f"[visual_capture] screenshot loop stopped. Total: {count} screenshots",
            file=sys.stderr,
        )

    def _start_ffmpeg(self) -> None:
        """Launch ffmpeg to capture the Xvfb display as an H.264 mp4.

        Key flags:
        -movflags +faststart  — writes the moov atom (MP4 index) at the
                                START of the file so browsers can begin
                                playback immediately and seek freely without
                                downloading the whole file first.
        """
        self._video_path = os.path.join(self.out_dir, "screen.mp4")
        # Temporary path — ffmpeg writes here, then we remux with faststart.
        tmp_path = self._video_path + ".tmp.mp4"
        log_path = os.path.join(self.out_dir, "video_capture.log")
        cmd = [
            "ffmpeg", "-y",
            # Input: X11 display (Xvfb virtual framebuffer)
            "-f", "x11grab",
            "-r", "2",                       # 2 fps — good balance of quality vs. disk
            "-s", "1920x1080",
            "-i", f":{self.display_num}.0",
            # Downscale to 720p for smaller file size
            "-vf", "scale=1280:720",
            # H.264 encoding — ultrafast for minimal CPU load on the bot
            "-codec:v", "libx264",
            "-preset", "ultrafast",
            "-crf", "28",                    # quality/size tradeoff (28 = acceptable)
            # IMPORTANT: yuv420p (4:2:0) is required for browser compatibility.
            # Without this, libx264 with ultrafast defaults to yuv444p which is
            # NOT supported by Chrome/Firefox/Safari → black video in the browser.
            "-pix_fmt", "yuv420p",
            "-profile:v", "high",
            "-level:v", "4.0",
            # faststart: move moov atom to file start so browsers can seek
            "-movflags", "+faststart",
            tmp_path,
        ]
        self._tmp_path = tmp_path
        try:
            with open(log_path, "w") as log_file:
                self._ffmpeg_proc = subprocess.Popen(
                    cmd,
                    stdout=log_file,
                    stderr=log_file,
                )
            print(
                f"[visual_capture] ffmpeg started (pid {self._ffmpeg_proc.pid}) "
                f"→ {self._video_path}",
                file=sys.stderr,
            )
        except Exception as exc:
            print(
                f"[visual_capture] failed to start ffmpeg: {exc} — "
                "continuing without video capture",
                file=sys.stderr,
            )
            self._ffmpeg_proc = None
            self._video_path = None

    async def _remux_faststart(self, src: str, dst: str) -> bool:
        """Remux src → dst with -movflags +faststart (stream-copy, no re-encode).

        Moves the MP4 moov atom from the end of the raw capture to the start
        so browsers can start playback and seek immediately.  Runs in a thread
        executor to avoid blocking the asyncio event loop.

        Returns True on success, False on any failure.
        """
        def _run() -> bool:
            cmd = [
                "ffmpeg", "-y",
                "-i", src,
                "-c", "copy",             # stream copy — no re-encode
                "-movflags", "+faststart", # moov atom at start of file
                dst,
            ]
            try:
                res = subprocess.run(
                    cmd,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.PIPE,
                    text=True,
                    timeout=120,          # cap at 2 min even for huge files
                )
                if res.returncode == 0:
                    return True
                print(
                    f"[visual_capture] faststart remux exited {res.returncode}: "
                    f"{res.stderr[-300:]}",
                    file=sys.stderr,
                )
                return False
            except Exception as exc:
                print(
                    f"[visual_capture] faststart remux exception: {exc}",
                    file=sys.stderr,
                )
                return False

        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(None, _run)

    async def _notify_backend(self, video_path: str) -> None:

        """POST to /api/recordings/{id}/video-ready so the DB is updated."""
        try:
            async with httpx.AsyncClient(timeout=10) as c:
                resp = await c.post(
                    f"{BACKEND_URL}/api/recordings/{self.recording_id}/video-ready",
                    json={"video_path": video_path},
                )
                if resp.status_code == 200:
                    print(
                        "[visual_capture] backend notified — video_path stored in DB",
                        file=sys.stderr,
                    )
                else:
                    print(
                        f"[visual_capture] backend /video-ready returned "
                        f"{resp.status_code}: {resp.text[:200]}",
                        file=sys.stderr,
                    )
        except Exception as exc:
            print(
                f"[visual_capture] failed to notify backend: {exc}",
                file=sys.stderr,
            )
