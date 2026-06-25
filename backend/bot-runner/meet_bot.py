"""
Google Meet bot — joins a Meet session via Playwright as a named guest.
Shares the same audio infrastructure as TeamsBot.
"""
import asyncio
import audioop
import base64
import os
import struct as _struct
import subprocess
import sys
import time
from playwright.async_api import async_playwright, Page, TimeoutError as PWTimeout

# JavaScript injected before Meet loads.  Uses WebRTC Insertable Streams
# (RTCRtpReceiver.createEncodedStreams) to tap encoded Opus frames BEFORE
# Chromium's audio decoder runs.  In headless Xvfb Chromium the decoder
# never produces real PCM (no audio device → silent output); intercepting
# at the encoded layer bypasses that entirely.
#
# Each RTCPeerConnection is forced to be created with
# encodedInsertableStreams=true.  For every incoming remote audio track we
# tap its receiver's encoded stream, forward each Opus packet to Python
# via the exposed `zapperOpusFrame(trackId, length, base64Packet)`, then
# pass the frame through unchanged so Meet's UI keeps working.
_JS_AUDIO_INTERCEPTOR = r"""
(function () {
    'use strict';
    const _Orig = window.RTCPeerConnection;
    if (!_Orig) return;

    let _trackCounter = 0;
    window._zReceiverSeen = window._zReceiverSeen || new WeakSet();

    function _b64encode(bytes) {
        let s = '';
        const CHUNK = 8192;
        for (let i = 0; i < bytes.length; i += CHUNK) {
            s += String.fromCharCode.apply(null, bytes.subarray(i, i + CHUNK));
        }
        return btoa(s);
    }

    // WebRTC track-ID → Zapper track-ID map for DOM name resolution.
    window._zRtcToZapper = window._zRtcToZapper || {};
    // Last reported name per Zapper track-ID — allows updating when a better
    // name becomes available (e.g. initially partial, then full name).
    window._zLastReportedName = window._zLastReportedName || {};

    // Helper to clean display names of bot/UI noise.
    function _cleanName(s) {
        return (s || '')
            .replace(/\s+/g, ' ')
            .replace(/\(You\)/gi, '')
            .replace(/\(Guest\)/gi, '')
            .replace(/\(External\)/gi, '')
            .replace(/Muted|Unmuted|Camera (on|off)/gi, '')
            .trim();
    }

    // Report a name for a Zapper track ID.  Only calls the Python bridge when
    // the name is new or different from the last reported value, and passes
    // basic sanity checks (length, not a bot/placeholder/technical/code name).
    function _reportTrackName(zapperId, rawName) {
        if (!rawName) return;
        var name = String(rawName).trim();
        if (name.length < 2 || name.length > 80) return;
        
        // Human names have at most 4 words.  Any string with 5+ words is
        // almost certainly a UI label or sentence, not a participant name.
        if (name.split(/\s+/).length > 4) return;

        // Skip the bot's own display name (injected at page init via window._zBotName)
        // and any extra account names registered in window._zBotAccountNames.
        var _nameLower = name.toLowerCase();
        if (window._zBotName && _nameLower === window._zBotName.toLowerCase()) return;
        if (window._zBotAccountNames) {
            for (var _bi = 0; _bi < window._zBotAccountNames.length; _bi++) {
                if (_nameLower === (window._zBotAccountNames[_bi] || '').toLowerCase()) return;
            }
        }

        // Skip placeholder / bot / generic UI names.
        if (/^(zapper|recorder|bot|you|\(you\)|user profile picture|avatar|photo|unknown\s*\d*|aditya\s*arnav)$/i.test(name)) return;
        
        // Skip brand / product / logo names — Google Meet puts "Meet logo" as
        // img alt text and it leaks through DOM walks.
        if (/\blogo\b/i.test(name)) return;
        if (/^(google meet|meet|google|chrome|chromium)$/i.test(name)) return;
        
        // Skip waiting-room / lobby placeholder strings.
        if (/please wait until/i.test(name)) return;
        if (/waiting for (the )?host/i.test(name)) return;
        if (/host brings you/i.test(name)) return;
        if (/asking to (be admitted|join)/i.test(name)) return;

        // Skip Google Meet control-bar / UI action strings.
        // These appear as aria-label on buttons, toolbars, and captions panels.
        if (/\b(notification|action|feature|control|setting|option|reaction|effect|background|spotlight|captions?|subtitle|record|present|transcript|layout|noise cancell)\b/i.test(name)) return;
        if (/\b(call|meeting|session|room)\b.*(feature|notif|action)/i.test(name)) return;
        
        // Skip technical GUIDs / UUIDs.
        if (/^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i.test(name)) return;
        
        // Skip technical track labels (e.g., "mainAudio-23001").
        if (/^(mainAudio|audio|video|track|stream|mic|camera)([-_\s\d]|$)/i.test(name)) return;
        
        // Skip leaks of scripts, ligatures or styling snippets.
        if (name.indexOf(';') !== -1 || name.indexOf('&&') !== -1 || name.indexOf('()') !== -1 || name.indexOf('{') !== -1 || name.indexOf('}') !== -1) return;
        if (/^[a-z_]+$/.test(name) && name.length < 20) return;
        
        // Only call Python bridge when name is new or changed.
        if (window._zLastReportedName[zapperId] === name) return;
        window._zLastReportedName[zapperId] = name;
        try { window.zapperTrackName(zapperId, name); } catch (e) {}
    }

    // Extract a participant display name from a DOM element.
    // Supports both Microsoft Teams and Google Meet.
    function _extractName(el) {
        if (!el) return '';
        const isTeams = window.location.hostname.indexOf('teams') !== -1;

        if (isTeams) {
            // ── Microsoft Teams Name Extraction ──
            
            // 1. Check data-tid participant display name children first
            var nameEl = el.querySelector('[data-tid="participant-display-name"], [data-tid*="display-name"], [class*="displayName"], [class*="name"]');
            if (nameEl && nameEl.textContent) {
                var s = _cleanName(nameEl.textContent);
                if (s.toLowerCase().indexOf('please wait until') !== -1 || s.toLowerCase().indexOf('waiting for host') !== -1) return '';
                if (s.length >= 2 && s.length <= 80) return s;
            }
            
            // 2. Check aria-label attribute of the tile or element itself
            var aria = el.getAttribute('aria-label') || '';
            if (aria) {
                var s = _cleanName(aria.split(',')[0]);
                if (s.length >= 2 && s.length <= 80) return s;
            }
            
            // 3. Fallback to image alt
            var img = el.querySelector('img[alt]');
            if (img && img.alt) {
                var s = _cleanName(img.alt);
                if (s.length >= 2 && s.length <= 80) return s;
            }
        } else {
            // ── Google Meet Name Extraction ──
            
            // 1. aria-label — Meet uses "Name's video", "Name's screen", etc.
            var s = el.getAttribute('aria-label') || '';
            if (s) {
                s = s.replace(/'s\s*(video|screen|camera|audio|microphone|presentation)\b[^,]*/i, '');
                s = s.split(',')[0].replace(/\(you\)/gi, '').trim();
                if (s.toLowerCase().indexOf('please wait until') !== -1 || s.toLowerCase().indexOf('waiting for host') !== -1) return '';
                if (s.length >= 2 && s.length <= 80) return s;
            }
            // 2. data-display-name attribute.
            s = (el.getAttribute('data-display-name') || '').trim();
            if (s.length >= 2 && s.length <= 80) return s;
            // 3. data-participant-name attribute.
            s = (el.getAttribute('data-participant-name') || '').trim();
            if (s.length >= 2 && s.length <= 80) return s;
            // 4. img[alt] inside this element — but skip branding images
            //    (e.g. "Meet logo", "Google logo") that are not participant names.
            var img = el.querySelector('img[alt]');
            if (img && img.alt
                    && !/^(avatar|photo)$/i.test(img.alt)
                    && !/\blogo\b/i.test(img.alt)
                    && !/^(google meet|meet|google|chrome)$/i.test(img.alt)) {
                s = img.alt.trim();
                if (s.length >= 2 && s.length <= 80) return s;
            }
        }
        return '';
    }

    // Walk up the DOM tree (max 12 levels) from el looking for a name.
    // Supports both platforms via the updated _extractName.
    function _extractNameWalking(el) {
        var cursor = el;
        for (var i = 0; i < 12 && cursor; i++) {
            var n = _extractName(cursor);
            if (n) return n;
            cursor = cursor.parentElement;
        }
        return '';
    }

    // Poll participant names and map them to Zapper track IDs.
    function _startNamePoller() {
        if (window._zNamePollerStarted) return;
        window._zNamePollerStarted = true;

        // Track when the poller started so we can use a faster interval early on.
        var _pollerStart = Date.now();
        var _FAST_WINDOW_MS = 30000; // first 30 s: poll every 500 ms
        var _FAST_INTERVAL_MS = 500;
        var _SLOW_INTERVAL_MS = 2000;

        // Shared polling function used by both the fast and slow timers.
        // Runs Strategy 1 (audio srcObject walk), Strategy 2 (participant tiles),
        // Strategy 3 (track.label), and Strategy 4 (direct receiver query).
        function _pollNames() {
            try {
                if (typeof window.zapperTrackName !== 'function') return;
                const isTeams = window.location.hostname.indexOf('teams') !== -1;

                // ── Strategy 1: audio element → DOM walk ─────────────────────────
                document.querySelectorAll('audio').forEach(function (audioEl) {
                    if (!audioEl.srcObject) return;
                    audioEl.srcObject.getAudioTracks().forEach(function (track) {
                        var zapperId = window._zRtcToZapper[track.id];
                        if (!zapperId) return;
                        var name = _extractNameWalking(audioEl);
                        if (!isTeams && !name && track.label && track.label.length >= 2
                                && track.label.length <= 80
                                && !/^\d+$/.test(track.label)) {
                            name = track.label;
                        }
                        if (name) _reportTrackName(zapperId, name);
                    });
                });

                // ── Strategy 2: participant tiles ─────────────────────────────────
                var tileSelectors = isTeams
                    ? '[data-tid="participant-tile"], [data-cid*="participant"], [class*="videoTile"], [class*="video-tile"], [class*="participantVideo"]'
                    // Google Meet: [data-participant-id] is the standard tile selector
                    // but also try [jsmodel], [data-requested-participant-id], and any
                    // element whose aria-label contains a name (Meet's headless tiles
                    // often lack data-participant-id but still have aria-label).
                    : '[data-participant-id], [data-requested-participant-id], [jsmodel][aria-label]';

                document.querySelectorAll(tileSelectors).forEach(function (tile) {
                    var name = _extractName(tile);
                    if (!name) return;
                    var audioEl = tile.querySelector('audio');
                    if (audioEl && audioEl.srcObject) {
                        audioEl.srcObject.getAudioTracks().forEach(function (track) {
                            var zapperId = window._zRtcToZapper[track.id];
                            if (zapperId) _reportTrackName(zapperId, name);
                        });
                    }
                    // Even without an <audio> element inside the tile, try to match
                    // by walking all registered receivers and finding the one whose
                    // track stream ID appears inside this tile's media.
                    try {
                        if (window._zRtcPeers) {
                            window._zRtcPeers.forEach(function (pc) {
                                try {
                                    pc.getReceivers().forEach(function (recv) {
                                        if (!recv.track || recv.track.kind !== 'audio') return;
                                        var zapperId = window._zRtcToZapper[recv.track.id];
                                        if (!zapperId) return;
                                        // If the receiver's MediaStream contains a track that
                                        // is connected to an audio element in this tile, the
                                        // tile name belongs to this zapperId.
                                        var streams = recv.getParameters ? [] : [];
                                        try { streams = pc.getRemoteStreams ? pc.getRemoteStreams() : []; } catch(e) {}
                                        streams.forEach(function (stream) {
                                            stream.getAudioTracks().forEach(function (t) {
                                                if (t.id === recv.track.id && !window._zLastReportedName[zapperId]) {
                                                    // Heuristic: if only 1 tile and 1 receiver
                                                    // we can attribute directly.
                                                    if (name) _reportTrackName(zapperId, name);
                                                }
                                            });
                                        });
                                    });
                                } catch (e) {}
                            });
                        }
                    } catch (e) {}
                });

                // ── Strategy 3: track.label on audio elements (Google Meet only) ──
                if (!isTeams) {
                    document.querySelectorAll('audio').forEach(function (audioEl) {
                        if (!audioEl.srcObject) return;
                        audioEl.srcObject.getAudioTracks().forEach(function (track) {
                            var zapperId = window._zRtcToZapper[track.id];
                            if (!zapperId || window._zLastReportedName[zapperId]) return;
                            var lbl = (track.label || '').trim();
                            if (lbl.length >= 2 && lbl.length <= 80 && /\s/.test(lbl)) {
                                _reportTrackName(zapperId, lbl);
                            }
                        });
                    });
                }

                // ── Strategy 4: tile aria-label correlation ───────────────────────
                // Some Google Meet headless tiles expose the participant name in
                // the tile's own aria-label without an <audio> child.
                // IMPORTANT: scope to [data-participant-id] tile roots ONLY —
                // scanning document-wide hits UI controls like
                // "Call feature notifications and actions".
                if (!isTeams) {
                    try {
                        var tileroots = document.querySelectorAll(
                            '[data-participant-id], [data-requested-participant-id]'
                        );
                        tileroots.forEach(function (tile) {
                            var rawLabel = (tile.getAttribute('aria-label') || '').trim();
                            if (!rawLabel) {
                                var child = tile.querySelector('[aria-label]');
                                if (child) rawLabel = (child.getAttribute('aria-label') || '').trim();
                            }
                            if (!rawLabel || rawLabel.length < 2 || rawLabel.length > 80) return;
                            var name = rawLabel
                                .replace(/'s\s*(video|screen|camera|audio|microphone|presentation)\b[^,]*/i, '')
                                .split(',')[0].replace(/\(you\)/gi, '').trim();
                            if (!name || name.length < 2) return;
                            var audioEl = tile.querySelector('audio');
                            if (audioEl && audioEl.srcObject) {
                                audioEl.srcObject.getAudioTracks().forEach(function (track) {
                                    var zapperId = window._zRtcToZapper[track.id];
                                    if (zapperId) _reportTrackName(zapperId, name);
                                });
                            }
                        });
                    } catch (e) {}
                }

            } catch (e) {}
        }

        // ── Fast initial burst (every 500 ms for first 30 s) ─────────────────
        // Immediately fires once so we don't wait 500 ms for the first attempt.
        _pollNames();
        var _fastTimer = setInterval(function () {
            _pollNames();
            if (Date.now() - _pollerStart >= _FAST_WINDOW_MS) {
                clearInterval(_fastTimer);
                // Hand off to the slower steady-state pollers below.
            }
        }, _FAST_INTERVAL_MS);

        // ── Slow steady-state pollers (run forever after initial burst) ───────
        setInterval(_pollNames, _SLOW_INTERVAL_MS);
        setInterval(_pollNames, 3000);
        setInterval(_pollNames, 6000);
    }

    function _tapReceiver(receiver, trackLabel) {
        if (window._zReceiverSeen.has(receiver)) return;
        window._zReceiverSeen.add(receiver);

        const trackId = 't' + (++_trackCounter);
        // Register WebRTC track ID so the name poller can correlate it to a DOM tile.
        if (receiver.track && receiver.track.id) {
            window._zRtcToZapper[receiver.track.id] = trackId;
        }
        try {
            if (typeof receiver.createEncodedStreams !== 'function') {
                console.error('[zapper] createEncodedStreams not available on receiver for '
                              + trackId);
                return;
            }
            const { readable, writable } = receiver.createEncodedStreams();
            const transform = new TransformStream({
                transform(frame, controller) {
                    try {
                        const bytes = new Uint8Array(frame.data);
                        window.zapperOpusFrame(trackId, bytes.length, _b64encode(bytes));
                    } catch (e) {
                        // Swallow — never break the media path.
                    }
                    controller.enqueue(frame);
                }
            });
            readable.pipeThrough(transform).pipeTo(writable).catch(function (e) {
                console.warn('[zapper] insertable stream pipe ended for ' + trackId + ':', e);
            });
            console.log('[zapper] Encoded-stream tap attached to ' + trackId
                        + ' (label=' + trackLabel + ')');
        } catch (err) {
            console.error('[zapper] tapReceiver failed for ' + trackId + ':', err);
        }
    }

    window.RTCPeerConnection = function (config, ...rest) {
        config = config || {};
        config.encodedInsertableStreams = true;
        const pc = new _Orig(config, ...rest);
        // Register PC so _startNamePoller's Strategy 4 can call pc.getReceivers()
        // directly without needing a <audio srcObject> in the DOM.
        window._zRtcPeers = window._zRtcPeers || new Set();
        window._zRtcPeers.add(pc);
        pc.addEventListener('connectionstatechange', function () {
            if (pc.connectionState === 'closed' || pc.connectionState === 'failed') {
                try { window._zRtcPeers.delete(pc); } catch(e) {}
            }
        });
        pc.addEventListener('track', function (evt) {
            if (!evt.track || evt.track.kind !== 'audio') return;
            _tapReceiver(evt.receiver, evt.track.label || '');
        });
        _startNamePoller();
        // Also poll receivers periodically: Teams' SFU client sometimes
        // adds receivers without firing 'track' on the wrapped PC.
        try {
            const _poll = setInterval(function () {
                try {
                    const recs = pc.getReceivers ? pc.getReceivers() : [];
                    for (const r of recs) {
                        if (r && r.track && r.track.kind === 'audio') {
                            _tapReceiver(r, r.track.label || '');
                        }
                    }
                } catch (e) { /* ignore */ }
            }, 1000);
            // Stop polling when the PC closes.
            pc.addEventListener('connectionstatechange', function () {
                if (pc.connectionState === 'closed') clearInterval(_poll);
            });
        } catch (e) { /* ignore */ }
        return pc;
    };
    window.RTCPeerConnection.prototype = _Orig.prototype;
    Object.setPrototypeOf(window.RTCPeerConnection, _Orig);

    // Belt & suspenders: also wrap RTCRtpReceiver.prototype.createEncodedStreams
    // so Teams clients that bypass our PC wrapper still get tapped.
    try {
        const _Recv = window.RTCRtpReceiver;
        if (_Recv && _Recv.prototype && typeof _Recv.prototype.createEncodedStreams === 'function') {
            const _origCreate = _Recv.prototype.createEncodedStreams;
            _Recv.prototype.createEncodedStreams = function () {
                const streams = _origCreate.apply(this, arguments);
                try {
                    if (this.track && this.track.kind === 'audio'
                        && !window._zReceiverSeen.has(this)) {
                        window._zReceiverSeen.add(this);
                        const trackId = 't' + (++_trackCounter);
                        const transform = new TransformStream({
                            transform(frame, controller) {
                                try {
                                    const bytes = new Uint8Array(frame.data);
                                    window.zapperOpusFrame(trackId, bytes.length, _b64encode(bytes));
                                } catch (e) {}
                                controller.enqueue(frame);
                            }
                        });
                        streams.readable.pipeThrough(transform).pipeTo(streams.writable)
                            .catch(function () {});
                        console.log('[zapper] createEncodedStreams tap attached to ' + trackId);
                    }
                } catch (e) {
                    console.warn('[zapper] createEncodedStreams wrap failed:', e);
                }
                return streams;
            };
        }
    } catch (e) { /* ignore */ }

    console.log('[zapper] RTCPeerConnection interceptor installed (insertable-streams mode)');
})();
"""


# Active-speaker DOM tracker REMOVED 2026-04 — Meet's speaking-marker
# selector matched the static highlight on the pinned tile, producing
# wildly wrong attribution (Prabhu logged 465x in a row, phantom names,
# inverted Track A/B labels).  Speaker attribution now happens in the
# worker via voice fingerprinting (SpeechBrain ECAPA-TDNN) over the
# per-track WAVs the JS interceptor already produces.  See
# zapper/worker/tasks/match_speakers.py.


from audio_setup import BotEnvironment, create_bot_environment
from audio_capture import AudioCapture
from audio_output import AudioOutput
from live_context import LiveTranscriptBuffer
from meeting_controller import MeetingController
from bot_api_client import BotAPIClient

import re as _re_ui

# Words / patterns that appear in Google Meet UI labels but never in a
# real participant's display name.
_MEET_UI_RE = _re_ui.compile(
    r'\b(options|effects|backgrounds|spotlight|presenting|reaction'
    r'|tile|emoji|notification|settings|more actions'
    r'|might still|full video|others might|others still'
    r'|unmute|mute|remove|pin|minimize|admit|deny|raise hand'
    r'|host|co-host|kicked|screen share|camera|microphone'
    r'|open in|full screen|new window|context menu|right click'
    r'|turn on|turn off|apply|cancel|save|dismiss|close|zoom in|zoom out)\b',
    _re_ui.IGNORECASE,
)

# Contractions that appear in toast/notification strings but not real names.
_TOAST_CONTRACTION_RE = _re_ui.compile(r"\b(can't|won't|don't|didn't|you're|you've|isn't|aren't)\b", _re_ui.IGNORECASE)


def _is_meet_ui_string(name: str) -> bool:
    """Return True when *name* looks like a Google Meet UI label rather than
    a real participant display name.

    Heuristics (any one is sufficient to reject):
    - Ends with a sentence terminator (notification toast text).
    - More than 5 whitespace-delimited tokens (sentences, not names).
    - Contains a known Meet action / UI keyword.
    - Contains a contraction like "can't", "won't" (toast messages, not names).
    """
    if not name:
        return True
    if name[-1] in ('.', '!', '?'):
        return True
    if len(name.split()) > 5:
        return True
    if _MEET_UI_RE.search(name):
        return True
    if _TOAST_CONTRACTION_RE.search(name):
        return True
    return False

BOT_DISPLAY_NAME = os.getenv("BOT_DISPLAY_NAME", "Zapper Recorder")
LOBBY_TIMEOUT = int(os.getenv("BOT_LOBBY_TIMEOUT_SECONDS", "300"))


class MeetBot:
    def __init__(self, recording_id: str, meeting_url: str, slot: int, settings: dict = None):
        self.recording_id = recording_id
        self.meeting_url = meeting_url
        self.participants: list[str] = []
        self._participants_seen: set[str] = set()
        # Track the bot's own Google-account display name (may differ from
        # BOT_DISPLAY_NAME, e.g. "Aditya Arnav" vs "Zapper Recorder").
        # Populated when we detect 'More options for <name>' in the DOM.
        self._bot_account_names: set[str] = set()
        self.slot = slot
        self.settings = settings or {}
        self.env: BotEnvironment = create_bot_environment(slot)
        self.api = BotAPIClient(recording_id)
        self.audio_q: asyncio.Queue = asyncio.Queue(maxsize=1000)
        self.live_q: asyncio.Queue = asyncio.Queue(maxsize=1000)

        self.bot_display_name = self.get_setting("bot_name", "BOT_DISPLAY_NAME", "Zapper Recorder")
        self.lobby_timeout = self.get_setting("lobby_timeout_seconds", "BOT_LOBBY_TIMEOUT_SECONDS", 300, type_cast=int)
        self.min_meeting_seconds = self.get_setting("min_meeting_seconds", "BOT_MIN_MEETING_SECONDS", 120, type_cast=int)
        self.max_alone_seconds = self.get_setting("max_alone_seconds", "BOT_MAX_ALONE_SECONDS", 60, type_cast=int)
        self.auto_leave_when_alone = self.get_setting("auto_leave_when_alone", "BOT_AUTO_LEAVE_WHEN_ALONE", True, type_cast=bool)
        # Visual capture mode — set per-meeting in the "Record a meeting" modal.
        self.visual_capture_mode: str = str(
            self.get_setting("visual_capture_mode", "VISUAL_CAPTURE_MODE", "disabled")
        ).strip().lower()

    def get_setting(self, key: str, env_var: str, default, type_cast=str):
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

    async def _on_scraper_participants(self, names: list[str], participant_first_seen: dict = None):
        bot_env_name = self.bot_display_name.strip().lower()
        updated = False
        for n in names:
            n_clean = n.strip()
            if not n_clean:
                continue
            nl = n_clean.lower()
            if nl == bot_env_name or (self_lower and nl == self_lower):
                continue
            if nl in {"you", "(you)"}:
                continue
            # Reject Google Meet UI strings (menu items, toasts, button
            # aria-labels) that pass the DOM extraction but are not names.
            if _is_meet_ui_string(n_clean):
                print(f"[meet-bot] Skipping UI string (not a participant): {n_clean!r}", file=sys.stderr)
                # Extract the Google account name from 'More options for <name>'
                # so we can block it from being attributed as a speaker.
                import re as _re_more
                _mo = _re_more.match(r'^More options for (.+)$', n_clean, _re_more.I)
                if _mo:
                    _acct = _mo.group(1).strip()
                    if _acct and _acct.lower() not in {bot_env_name, self_lower}:
                        # This is the bot's Google-account name.
                        if _acct not in self._bot_account_names:
                            self._bot_account_names.add(_acct)
                            print(
                                f"[meet-bot] Detected bot Google-account name: '{_acct}'",
                                file=sys.stderr,
                            )
                continue
            if n_clean not in self._participants_seen:
                self._participants_seen.add(n_clean)
                self.participants.append(n_clean)
                # Record the wall-clock time this participant was first seen.
                # Used by _temporal_correlate_track for reliable track→name mapping.
                if participant_first_seen is not None and n_clean not in participant_first_seen:
                    participant_first_seen[n_clean] = time.time()
                print(f"[meet-bot] Participant detected via scraper: {n_clean}", file=sys.stderr)
                updated = True
        if updated:
            await self.api.update_participants(self.participants)
            # Retroactively rename 'Speaker' segments to this participant's name
            # if they were transcribed before the name poller caught up.
            if len(self.participants) == 1:
                await self.api.rename_speaker("Speaker", self.participants[0])

    async def run(self):
        await self.api.update_status("joining")
        async with async_playwright() as pw:
            # Inherit full environment so libpulse/Chromium can find HOME, PATH, etc.
            # Then override display and audio routing to our per-slot virtual devices.
            chromium_env = {**os.environ}
            chromium_env["DISPLAY"] = f":{self.env.display_num}"
            chromium_env["PULSE_SERVER"] = f"unix:{self.env.pulse_socket}"
            chromium_env["PULSE_SINK"] = self.env.sink_name
            chromium_env["PULSE_SOURCE"] = f"{self.env.sink_name}.monitor"
            chromium_env["PULSE_LATENCY_MSEC"] = "30"
            # auth-anonymous=1 on the socket means no cookie needed
            chromium_env["PULSE_COOKIE"] = f"/tmp/pulse-config-{self.env.slot}/pulse.cookie"

            browser = await pw.chromium.launch(
                executable_path="/usr/bin/chromium",
                headless=False,
                args=[
                    f"--display=:{self.env.display_num}",
                    "--no-sandbox",
                    "--disable-setuid-sandbox",
                    "--use-fake-ui-for-media-stream",
                    # Provide a fake mic/camera device.  Without this Chromium
                    # has no audio device, the WebRTC audio pipeline never
                    # initializes, and remote audio packets are received but
                    # never decoded.
                    "--use-fake-device-for-media-stream",
                    # Feed silent audio to the fake mic so participants don't
                    # hear Chromium's default sine-wave test tone.
                    "--use-file-for-fake-audio-capture=/opt/silence.wav",
                    # Enable RTCRtpReceiver.createEncodedStreams so we can tap
                    # encoded Opus frames before Chromium's audio decoder runs
                    # (the decoder is broken in headless Xvfb mode).
                    "--enable-blink-features=WebRTCInsertableStreams,RTCRtpScriptTransform",
                    "--enable-features=RTCEncodedTransform",
                    "--autoplay-policy=no-user-gesture-required",
                    "--disable-gpu",
                    "--disable-dev-shm-usage",
                    # Run audio in main process so it can use PULSE_SERVER socket
                    "--disable-features=AudioServiceSandbox,AudioServiceOutOfProcess",
                    # Helps avoid Google bot detection
                    "--disable-blink-features=AutomationControlled",
                    "--lang=en-US",
                ],
                env=chromium_env,
            )
            session_path = os.getenv("BOT_SESSION_PATH", "/data/recordings/google_session.json")
            ctx_kwargs = dict(
                permissions=["microphone", "camera"],
                user_agent=(
                    "Mozilla/5.0 (X11; Linux x86_64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/124.0.0.0 Safari/537.36"
                ),
                locale="en-US",
            )
            if os.path.exists(session_path):
                ctx_kwargs["storage_state"] = session_path
                print(f"[meet-bot] Loading saved Google session from {session_path}", file=sys.stderr)

            ctx = await browser.new_context(**ctx_kwargs)

            # ── JS audio capture setup (Insertable Streams / Opus) ──────────
            # Each call delivers one encoded Opus frame from one remote track.
            # We append them to a per-track binary file as
            # [u32 LE length][opus packet bytes] for later decoding.
            from pathlib import Path as _Path
            _storage = os.getenv("STORAGE_PATH", "/data/recordings")
            rec_dir = str(_Path(_storage) / self.recording_id)
            os.makedirs(rec_dir, exist_ok=True)
            opus_files: dict[str, object] = {}
            opus_counts: dict[str, int] = {}
            opus_bytes: dict[str, int] = {}
            from live_context import LiveTranscriptBuffer, get_active_speaker_name
            
            _live_engine = self.get_setting("live_engine", "LIVE_ENGINE", "whisper").strip().lower()
            if _live_engine not in ("captions", "whisper", "both"):
                _live_engine = "whisper"
            _run_whisper = _live_engine in ("whisper", "both")
            _live_per_track = self.get_setting("live_per_track", "LIVE_PER_TRACK", False, type_cast=bool)

            track_name_map: dict[str, str] = {}
            track_activity_map: dict[str, list[float]] = {}
            # Temporal correlation maps — used when DOM name poller fails.
            # track_first_active: wall-clock time of the first Opus frame per track.
            # participant_first_seen: wall-clock time when each participant name was
            # first scraped from the DOM.  Sorting both lists by time gives a much
            # more reliable track→name mapping than index ordering.
            track_first_active: dict[str, float] = {}
            participant_first_seen: dict[str, float] = {}
            
            def _get_master_speaker():
                name = get_active_speaker_name(track_activity_map, track_name_map)
                print(f"[meet-bot DEBUG] _get_master_speaker: resolved_name={name!r}, participants={self.participants}", file=sys.stderr)
                # If the resolved name is NOT a known participant (e.g. it resolved
                # to the bot's own Google account name like 'Aditya Arnav' which is
                # excluded from self.participants), treat it as the generic fallback.
                if name != "Speaker" and self.participants and name not in self.participants:
                    print(f"[meet-bot DEBUG] Track name {name!r} is not a known participant — demoting to 'Speaker'", file=sys.stderr)
                    name = "Speaker"
                # If the JS track→DOM name poller hasn't resolved a name yet
                # (returns the generic fallback) BUT we already know who is in
                # the meeting from the DOM participant scan, use that name.
                # This covers the common case where audio track IDs can't be
                # correlated to DOM tiles in Google Meet's headless layout:
                #   • exactly 1 known participant → must be them speaking
                if name == "Speaker" and len(self.participants) == 1:
                    print(f"[meet-bot DEBUG] Fallback activated: using {self.participants[0]!r}", file=sys.stderr)
                    return self.participants[0]
                return name

            def _temporal_correlate_track(track_id: str) -> str:
                """Map a track_id to a participant name using temporal ordering.

                When the JS DOM name poller fails (track_name_map empty), we sort
                tracks by the wall-clock time of their first Opus frame and
                participants by the time they first appeared in the DOM scrape.
                The earliest track maps to the earliest participant, second to
                second, etc.  This is far more reliable than the old index heuristic
                (which had a 50% chance of inversion with 2 participants).

                Returns a name string, or empty string if correlation is not yet
                possible (e.g. participant list is still empty).
                """
                pts = self.participants
                if not pts:
                    return ""
                if len(pts) == 1:
                    return pts[0]

                # Build a list of (first_active_time, track_id) sorted ascending.
                known_times = [
                    (t_time, tid)
                    for tid, t_time in track_first_active.items()
                ]
                known_times.sort(key=lambda x: x[0])

                # Build a list of (first_seen_time, name) for participants we've
                # timed.  Participants not yet in participant_first_seen fall back
                # to their list index as a tiebreaker (stable).
                named_times = [
                    (participant_first_seen.get(n, float('inf')), n)
                    for n in pts
                ]
                named_times.sort(key=lambda x: x[0])

                corr_map = {
                    tid: name
                    for (_, tid), (_, name) in zip(known_times, named_times)
                }
                matched = corr_map.get(track_id, "")
                if matched:
                    print(
                        f"[meet-bot] Temporal correlation: {track_id} → '{matched}' "
                        f"(tracks={[t for _, t in known_times]}, "
                        f"participants={[n for _, n in named_times]})",
                        file=sys.stderr,
                    )
                return matched

            live_buf = LiveTranscriptBuffer(recording_id=self.recording_id, get_speaker_fn=_get_master_speaker, settings=self.settings)

            track_buffers = {}
            track_queues = {}
            dynamic_tasks = []
            
            # Decoders for real-time PCM extraction
            decoders = {}

            # ── Participants sidecar ─────────────────────────────────────────
            # We used to maintain an active_speaker_log.jsonl + meta sidecar
            # populated by a JS DOM poller; that approach was abandoned (see
            # the big REMOVED comment near the JS interceptor for why).
            # Speaker attribution now happens in the worker via voice
            # fingerprinting on the per-track WAVs.  We still drop a slim
            # participants.json into the recording directory as a sanity-check
            # diagnostic — "who *should* be in the meeting".
            participants_path = os.path.join(rec_dir, "participants.json")

            def _opus_path(track_id: str) -> str:
                return os.path.join(rec_dir, f"audio_js_{track_id}.opus")

            async def _receive_opus_frame(track_id: str, length: int, b64: str) -> None:
                try:
                    pkt = base64.b64decode(b64)
                    import time
                    if track_id not in track_activity_map:
                        track_activity_map[track_id] = []
                    _now = time.time()
                    track_activity_map[track_id].append(_now)
                    # Record the time of the FIRST opus frame for this track so
                    # _temporal_correlate_track can map tracks → participants by
                    # arrival order instead of the unreliable index heuristic.
                    if track_id not in track_first_active:
                        track_first_active[track_id] = _now
                        print(
                            f"[meet-bot] First opus frame for {track_id} "
                            f"at t={_now:.3f} (track_first_active now: {dict(track_first_active)})",
                            file=sys.stderr,
                        )
                    fh = opus_files.get(track_id)
                    if fh is None:
                        fh = open(_opus_path(track_id), "wb")
                        opus_files[track_id] = fh
                        opus_counts[track_id] = 0
                        opus_bytes[track_id] = 0
                        print(
                            f"[meet-bot] opening opus stream file for {track_id}",
                            file=sys.stderr,
                        )
                    fh.write(_struct.pack("<I", len(pkt)))
                    fh.write(pkt)
                    opus_counts[track_id] += 1
                    opus_bytes[track_id] += len(pkt)
                    if opus_counts[track_id] % 500 == 0:
                        print(
                            f"[meet-bot] {track_id}: {opus_counts[track_id]} opus frames "
                            f"({opus_bytes[track_id]/1024:.1f} KB)",
                            file=sys.stderr,
                        )
                        
                    # Real-time decoding and LIVE_PER_TRACK
                    if _live_per_track:
                        import opuslib
                        if track_id not in decoders:
                            decoders[track_id] = opuslib.Decoder(48000, 1)
                        try:
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
                            samples_16k_raw = list(_struct.unpack(f"<{num_samples}h", resampled_bytes))
                                
                            now = time.time()
                            diff = now - decoders[track_id]._z_last_time
                            if diff > 0.15:
                                silence_sec = min(diff, 10.0)
                                silence_samples = [0] * int(silence_sec * 16000)
                                samples_16k = silence_samples + samples_16k_raw
                            else:
                                samples_16k = samples_16k_raw
                                
                            decoders[track_id]._z_last_time = now
                            
                            if track_id not in track_buffers:
                                q = asyncio.Queue(maxsize=1000)
                                track_queues[track_id] = q
                                def _get_spk(_t=track_id):
                                    # Priority 1: JS DOM-correlated name (most reliable).
                                    name = track_name_map.get(_t, "")
                                    if name:
                                        return name
                                    # Priority 2: Temporal correlation — sort tracks and
                                    # participants by first-seen time and assign by rank.
                                    # Far more reliable than the old index heuristic.
                                    name = _temporal_correlate_track(_t)
                                    if name:
                                        return name
                                    # Priority 3: Last resort — single-participant shortcut.
                                    pts = self.participants
                                    if not pts:
                                        return "Speaker"
                                    if len(pts) == 1:
                                        return pts[0]
                                    return "Speaker"
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
                                    print(f"[meet-bot] Started LIVE_PER_TRACK Whisper pipeline for {track_id}", file=sys.stderr)
                                    
                            try:
                                track_queues[track_id].put_nowait(samples_16k)
                            except asyncio.QueueFull:
                                pass
                        except Exception as decode_err:
                            if "corrupted stream" not in str(decode_err).lower():
                                print(f"[meet-bot] opus real-time decode error for {track_id}: {decode_err}", file=sys.stderr)
                            silence_16k = [0] * 320  # 20ms at 16kHz
                            now = time.time()
                            if track_id in decoders:
                                decoders[track_id]._z_last_time = now
                            if track_id in track_queues:
                                try:
                                    track_queues[track_id].put_nowait(silence_16k)
                                except asyncio.QueueFull:
                                    pass

                except Exception as exc:
                    print(f"[meet-bot] opus frame error: {exc}", file=sys.stderr)

            await ctx.expose_function("zapperOpusFrame", _receive_opus_frame)



            # Precompute the bot display-name in lower-case so _receive_track_name
            # can exclude it without a closure over self.bot_display_name.
            _bot_display_lower = self.bot_display_name.strip().lower()

            async def _receive_track_name(track_id: str, name: str) -> None:
                name = (name or "").strip()
                if not track_id or not name:
                    return
                # Silently ignore the bot's own Google-account name.
                # The bot appears as a tile in Google Meet ("Aditya Arnav" etc.)
                # and the JS poller may resolve its tile to a track ID.  We must
                # never attribute audio to the bot's own name.
                nl = name.lower()
                if nl == _bot_display_lower:
                    print(
                        f"[meet-bot] Ignoring bot's own name for track {track_id}: '{name}'",
                        file=sys.stderr,
                    )
                    return
                # Also block the bot's Google-account name (e.g. "Aditya Arnav")
                # which differs from BOT_DISPLAY_NAME.
                if any(nl == ban.lower() for ban in self._bot_account_names):
                    print(
                        f"[meet-bot] Ignoring bot account name for track {track_id}: '{name}'",
                        file=sys.stderr,
                    )
                    return
                # Also reject if the resolved name exactly matches the Google
                # account owner — the account name may differ from BOT_DISPLAY_NAME.
                # We detect this by checking whether this name was already tagged
                # as the bot's identity in the 'More options for <name>' UI string.
                # The safest proxy: if the name is NOT in self.participants (the
                # human-only list) and participants has already been populated,
                # it is either the bot or an unknown — drop it.
                if self.participants and name not in self.participants:
                    # Could be the bot's account name or a stale UI artifact.
                    print(
                        f"[meet-bot] Ignoring unrecognised track name '{name}' for {track_id} "
                        f"(not in participant list {self.participants})",
                        file=sys.stderr,
                    )
                    return
                old = track_name_map.get(track_id)
                if old == name:
                    return  # no change
                track_name_map[track_id] = name
                if old:
                    print(
                        f"[meet-bot] DOM name updated: {track_id} '{old}' → '{name}'",
                        file=sys.stderr,
                    )
                else:
                    print(
                        f"[meet-bot] DOM name resolved: {track_id} → '{name}'",
                        file=sys.stderr,
                    )

            await ctx.expose_function("zapperTrackName", _receive_track_name)

            page = await ctx.new_page()

            # Forward browser console messages so we can see '[zapper]' logs
            page.on("console", lambda msg: print(
                f"[browser] {msg.type}: {msg.text}", file=sys.stderr
            ) if "[zapper]" in msg.text else None)

            # Inject the bot's display name into the page so the JS name poller
            # can skip the bot's own participant tile without a Python round-trip.
            # We also inject the Google-account name if it differs (e.g. "Aditya Arnav"
            # vs "Zapper Recorder") — at this point we don't know the account name yet
            # but the Python side already filters it via _receive_track_name.
            import json as _json_bot
            _bot_name_script = (
                f"window._zBotName = {_json_bot.dumps(self.bot_display_name.strip())};"
            )
            await page.add_init_script(_bot_name_script)

            # Inject RTC interceptor BEFORE any Meet JS runs
            await page.add_init_script(_JS_AUDIO_INTERCEPTOR)

            has_session = os.path.exists(session_path)
            if has_session:
                print("[meet-bot] Loaded saved session from disk", file=sys.stderr)

            # Navigate to the Meet URL first
            await page.goto(self.meeting_url, wait_until="domcontentloaded", timeout=60_000)

            # We need to sign in if we have no session, OR if Google rejected our 
            # expired session and redirected us to a sign-in page.
            needs_signin = not has_session or "accounts.google.com" in page.url or "ServiceLogin" in page.url

            if needs_signin:
                print("[meet-bot] Session missing or expired — running sign-in flow", file=sys.stderr)
                
                # Delete stale session file if it exists
                if has_session:
                    try:
                        os.remove(session_path)
                    except OSError:
                        pass
                
                signed_in = await self._sign_in_google(page)
                if signed_in:
                    print("[meet-bot] Signed in — navigating to meeting as authenticated user", file=sys.stderr)
                    # Re-navigate to the meeting
                    await page.goto(self.meeting_url, wait_until="domcontentloaded", timeout=60_000)
                else:
                    print("[meet-bot] Sign-in failed — joining as guest", file=sys.stderr)
                    await page.goto(self.meeting_url, wait_until="domcontentloaded", timeout=60_000)

            # Handle pre-join UI
            await self._handle_prejoin(page)

            # Start audio recording before we're admitted
            capture = AudioCapture(self.recording_id, self.env)
            output = AudioOutput(self.env)
            await capture.start()

            # Wait until admitted into the meeting
            await self._wait_admitted(page)
            await self.api.update_status("recording")

            # live_buf and _get_master_speaker are initialized above before Opus capture
            controller = MeetingController(live_buf, self.recording_id, output, self.api)

            # Spawn infinite-loop tasks separately so we can cancel them when
            # the meeting ends (asyncio.gather blocks until ALL tasks finish).
            bg_tasks = [
                asyncio.create_task(capture.stream(self.audio_q)),
                asyncio.create_task(self._fanout_audio()),
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
                        f"[meet-bot] Visual capture started: mode={self.visual_capture_mode!r}",
                        file=sys.stderr,
                    )
                except Exception as _vc_exc:
                    print(
                        f"[meet-bot] Visual capture failed to start (non-fatal): {_vc_exc}",
                        file=sys.stderr,
                    )
                    _visual_capture = None
            if _run_whisper:
                if not _live_per_track:
                    bg_tasks.append(asyncio.create_task(live_buf.process(self.live_q)))
                    print(f"[meet-bot] LIVE_ENGINE={_live_engine!r}: Whisper live path ENABLED (mixed buffer)", file=sys.stderr)
                else:
                    bg_tasks.extend(dynamic_tasks)
                    print(f"[meet-bot] LIVE_ENGINE={_live_engine!r}: Whisper live path ENABLED (LIVE_PER_TRACK)", file=sys.stderr)
            else:
                print(f"[meet-bot] LIVE_ENGINE={_live_engine!r}: native captions only", file=sys.stderr)

            # Wait for the meeting to end (returns or raises)
            try:
                await self._watch_for_end(page, participant_first_seen=participant_first_seen)
                print("[meet-bot] Meeting ended — stopping recording", file=sys.stderr)
            except Exception as e:
                print(f"[meet-bot] Watch-for-end exited: {e}", file=sys.stderr)

            # Cancel all background tasks
            for t in bg_tasks:
                t.cancel()
            await asyncio.gather(*bg_tasks, return_exceptions=True)

            # Stop visual capture BEFORE finalizing audio (non-fatal).
            if _visual_capture is not None:
                try:
                    await _visual_capture.stop()
                except Exception as _vc_exc:
                    print(
                        f"[meet-bot] Visual capture stop error (non-fatal): {_vc_exc}",
                        file=sys.stderr,
                    )

            wav_path = await capture.stop()

            # ── Preserve PulseAudio capture and ALSO produce JS mix ─────────
            # We keep both files so we can diagnose which path actually
            # captures audio.  PulseAudio result -> audio_pulse.wav.  JS
            # mix -> audio_js.wav.  The "winner" (whichever has non-silent
            # audio) is copied to audio.wav at the end.
            rec_dir = os.path.dirname(wav_path)
            pulse_wav = os.path.join(rec_dir, "audio_pulse.wav")
            js_wav = os.path.join(rec_dir, "audio_js.wav")
            try:
                if os.path.exists(wav_path):
                    os.replace(wav_path, pulse_wav)
                    print(f"[meet-bot] PulseAudio capture saved: {pulse_wav}", file=sys.stderr)
            except Exception as exc:
                print(f"[meet-bot] Failed to preserve pulse wav: {exc}", file=sys.stderr)

            # Close all per-track Opus files written by the JS bridge.
            for tid, fh in list(opus_files.items()):
                try:
                    fh.close()
                except Exception:
                    pass

            # Drop a slim participants.json diagnostic sidecar.  The voice
            # fingerprinting matcher in the worker doesn't read this — it's
            # purely useful for humans debugging "did the bot see Alice in
            # the participant list?" after the fact.
            try:
                import json as _json
                with open(participants_path, "w") as _pf:
                    _json.dump({"participants": list(self.participants)}, _pf)
                print(
                    f"[meet-bot] participants.json written: "
                    f"{len(self.participants)} participant(s)",
                    file=sys.stderr,
                )
            except Exception as exc:
                print(f"[meet-bot] Failed to write participants.json: {exc}", file=sys.stderr)

            # Write track_names.json — primary source for match_speakers worker.
            # Maps Zapper track IDs (e.g. "t1") to real participant display names
            # resolved from the DOM via the JS name poller.
            try:
                import json as _json
                track_names_path = os.path.join(rec_dir, "track_names.json")
                with open(track_names_path, "w") as _tf:
                    _json.dump(track_name_map, _tf)
                if track_name_map:
                    print(
                        f"[meet-bot] track_names.json written: {track_name_map}",
                        file=sys.stderr,
                    )
                else:
                    print(
                        "[meet-bot] track_names.json written (empty — DOM name resolution found nothing)",
                        file=sys.stderr,
                    )
            except Exception as exc:
                print(f"[meet-bot] Failed to write track_names.json: {exc}", file=sys.stderr)

            # Write track_timing.json — used by the offline match_speakers worker
            # for temporal correlation when track_names.json is empty.
            # Maps Zapper track IDs to their first-Opus-frame wall-clock time, and
            # participant names to their first-DOM-scrape wall-clock time.
            try:
                import json as _json
                track_timing_path = os.path.join(rec_dir, "track_timing.json")
                with open(track_timing_path, "w") as _tt:
                    _json.dump({
                        "track_first_active": track_first_active,
                        "participant_first_seen": participant_first_seen,
                    }, _tt)
                print(
                    f"[meet-bot] track_timing.json written: "
                    f"tracks={list(track_first_active.keys())} "
                    f"participants={list(participant_first_seen.keys())}",
                    file=sys.stderr,
                )
            except Exception as exc:
                print(f"[meet-bot] Failed to write track_timing.json: {exc}", file=sys.stderr)

            if opus_files:
                from opus_decoder import decode_opus_file
                track_wavs: list[str] = []
                for track_id in opus_files:
                    opus_path = _opus_path(track_id)
                    track_wav = os.path.join(rec_dir, f"audio_js_{track_id}.wav")
                    try:
                        decoded, failed = decode_opus_file(opus_path, track_wav)
                        size_kb = os.path.getsize(track_wav) / 1024
                        print(
                            f"[meet-bot] {track_id}: decoded {decoded} frames "
                            f"({failed} failed) → {track_wav} ({size_kb:.1f} KB)",
                            file=sys.stderr,
                        )
                        if decoded > 0:
                            track_wavs.append(track_wav)
                    except Exception as exc:
                        print(
                            f"[meet-bot] opus decode failed for {track_id}: {exc}",
                            file=sys.stderr,
                        )

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
                                f"[meet-bot] JS audio → WAV OK ({len(track_wavs)} tracks): {js_wav}",
                                file=sys.stderr,
                            )
                        else:
                            print(
                                f"[meet-bot] ffmpeg mix failed:\n{result.stderr[-800:]}",
                                file=sys.stderr,
                            )
                    except Exception as exc:
                        print(f"[meet-bot] JS audio save error: {exc}", file=sys.stderr)
                else:
                    print("[meet-bot] No usable decoded WAVs", file=sys.stderr)
            else:
                print("[meet-bot] No JS opus frames captured", file=sys.stderr)

            # Pick the louder of the two as the canonical audio.wav.
            def _max_volume(path: str) -> float:
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

            pulse_db = _max_volume(pulse_wav)
            js_db = _max_volume(js_wav)
            print(f"[meet-bot] max_volume pulse={pulse_db} dB  js={js_db} dB", file=sys.stderr)

            winner = pulse_wav if pulse_db >= js_db else js_wav
            if os.path.exists(winner):
                import shutil
                shutil.copy(winner, wav_path)
                print(f"[meet-bot] Winner: {winner} → audio.wav", file=sys.stderr)

            wav_size = os.path.getsize(wav_path) if os.path.exists(wav_path) else 0
            print(f"[meet-bot] Recording saved: {wav_path} ({wav_size/1024/1024:.1f} MB)", file=sys.stderr)
            await self.api.update_status("processing")
            print(f"[meet-bot] Final participants: {self.participants}", file=sys.stderr)
            await self.api.upload_complete(wav_path, self.participants, audio_size_bytes=wav_size)
            print("[meet-bot] Pipeline triggered — transcription queued", file=sys.stderr)
            await browser.close()

    # ─── Google authentication ─────────────────────────────────────────────

    async def _sign_in_google(self, page: Page) -> bool:
        """
        Sign the bot into Google using BOT_GOOGLE_EMAIL + BOT_GOOGLE_PASSWORD env vars.
        Returns True if sign-in succeeded, False to fall back to guest mode.
        """
        email = os.getenv("BOT_GOOGLE_EMAIL", "")
        password = os.getenv("BOT_GOOGLE_PASSWORD", "")
        if not email or not password:
            print("[meet-bot] No BOT_GOOGLE_EMAIL/PASSWORD set — guest mode", file=sys.stderr)
            return False

        try:
            print(f"[meet-bot] Signing in as {email} ...", file=sys.stderr)
            
            # Clear any stale cookies so we get a clean sign-in page, not the account chooser
            await page.context.clear_cookies()
            
            await page.goto(
                "https://accounts.google.com/signin/v2/identifier?hl=en",
                wait_until="networkidle",
                timeout=30_000,
            )
            await self._screenshot(page, "00a_signin_start")

            # Enter email
            email_input = page.locator("input[type='email'], input[name='identifier'], #identifierId").first
            await email_input.wait_for(state="visible", timeout=15_000)
            await email_input.fill(email)
            await page.keyboard.press("Enter")
            await page.wait_for_timeout(2_000)
            await self._screenshot(page, "00b_after_email")

            # Enter password
            pwd_input = page.locator("input[type='password'][name='Passwd'], input[type='password']").first
            await pwd_input.wait_for(state="visible", timeout=15_000)
            await pwd_input.fill(password)
            await page.keyboard.press("Enter")
            await page.wait_for_timeout(3_000)
            await self._screenshot(page, "00c_after_password")

            print(f"[meet-bot] After password URL: {page.url}", file=sys.stderr)

            # If on a challenge page, extract and announce the number to pick
            if "challenge" in page.url:
                try:
                    import re as _re
                    body_text = await page.inner_text("body")
                    numbers = _re.findall(r'\b(\d{2})\b', body_text)
                    if numbers:
                        print(f"[meet-bot] *** PHONE CHALLENGE — pick number {numbers[0]} on your phone ***", file=sys.stderr)
                    else:
                        print("[meet-bot] *** PHONE CHALLENGE — approve the notification on your phone ***", file=sys.stderr)
                    await self._screenshot(page, "00c_challenge")
                except Exception:
                    pass

            # Wait up to 90 seconds for any challenge (phone/2FA) to be resolved
            print("[meet-bot] Waiting for sign-in to complete (approve phone prompt if shown)...", file=sys.stderr)
            deadline = time.time() + 90
            signed_in = False
            while time.time() < deadline:
                current = page.url
                # Success: landed somewhere that's not a sign-in or challenge page
                if (
                    "accounts.google.com/signin" not in current
                    and "ServiceLogin" not in current
                    and "challenge" not in current
                    and "accounts.google.com" in current
                ):
                    signed_in = True
                    break
                # Also success if we've been redirected fully away from accounts.google.com
                if "accounts.google.com" not in current:
                    signed_in = True
                    break
                await page.wait_for_timeout(2_000)

            await self._screenshot(page, "00c_final_signin")
            print(f"[meet-bot] Final sign-in URL: {page.url}", file=sys.stderr)

            if not signed_in:
                print("[meet-bot] Sign-in timed out — still on challenge page", file=sys.stderr)
                return False

            # Dismiss "Stay signed in?" or similar prompts
            for label in ["Yes", "Continue", "I agree", "Accept all"]:
                try:
                    btn = page.get_by_role("button", name=label)
                    if await btn.is_visible(timeout=3_000):
                        await btn.click()
                        await page.wait_for_timeout(1_500)
                except (PWTimeout, Exception):
                    pass

            # Save session state so future runs skip sign-in entirely
            session_path = os.getenv("BOT_SESSION_PATH", "/data/recordings/google_session.json")
            try:
                os.makedirs(os.path.dirname(session_path), exist_ok=True)
                await page.context.storage_state(path=session_path)
                print(f"[meet-bot] Session saved to {session_path}", file=sys.stderr)
            except Exception as save_err:
                print(f"[meet-bot] Could not save session: {save_err}", file=sys.stderr)

            print("[meet-bot] Google sign-in successful!", file=sys.stderr)
            return True

        except Exception as exc:
            print(f"[meet-bot] Google sign-in error: {exc}", file=sys.stderr)
            await self._screenshot(page, "00e_signin_exception")
            return False

    # ─── Pre-join handling ─────────────────────────────────────────────────

    async def _screenshot(self, page: Page, name: str):
        """Save a debug screenshot to /tmp/."""
        try:
            path = f"/tmp/zapper_bot_{name}.png"
            await page.screenshot(path=path)
            print(f"[meet-bot] Screenshot saved: {path}", file=sys.stderr)
        except Exception as ex:
            print(f"[meet-bot] Screenshot failed ({name}): {ex}", file=sys.stderr)

    async def _handle_prejoin(self, page: Page):
        """
        Google Meet pre-join flow:
          1. Optionally dismiss 'Continue without signing in'
          2. Fill in display name if prompted
          3. Turn off camera
          4. Click 'Join now' or 'Ask to join'
        """
        print(f"[meet-bot] Navigated to: {page.url}", file=sys.stderr)
        await page.wait_for_timeout(3_000)
        await self._screenshot(page, "01_after_nav")

        # Step 1: dismiss sign-in prompt if present
        for label in ["Continue without signing in", "Use without an account"]:
            try:
                btn = page.get_by_role("button", name=label)
                await btn.wait_for(timeout=5_000)
                print(f"[meet-bot] Clicking: {label}", file=sys.stderr)
                await btn.click()
                await page.wait_for_timeout(1_000)
                break
            except PWTimeout:
                continue

        await self._screenshot(page, "02_after_signin_dismiss")

        # Step 2: fill display name if the textbox appears
        try:
            name_input = page.get_by_role("textbox", name="Your name")
            await name_input.wait_for(timeout=10_000)
            print(f"[meet-bot] Filling name: {self.bot_display_name}", file=sys.stderr)
            await name_input.click()
            await page.keyboard.press("Control+a")
            await name_input.fill(self.bot_display_name)
            await page.wait_for_timeout(500)
        except PWTimeout:
            print("[meet-bot] No name input found (already signed in?)", file=sys.stderr)

        await self._screenshot(page, "03_after_name")

        # Step 3: dismiss any error popups (mic/camera not found)
        for close_label in ["Close", "Dismiss", "×", "close"]:
            try:
                close_btn = page.get_by_role("button", name=close_label)
                if await close_btn.is_visible(timeout=1_000):
                    await close_btn.click()
                    await page.wait_for_timeout(300)
            except (PWTimeout, Exception):
                pass
        # Also try clicking any toast/alert X buttons via CSS
        try:
            await page.locator("[aria-label='Close'], [data-mdc-dialog-action='close']").first.click(timeout=1_000)
        except Exception:
            pass

        # Step 4: turn off camera
        for cam_label in ["Turn off camera", "Camera"]:
            try:
                cam_btn = page.get_by_role("button", name=cam_label)
                if await cam_btn.is_visible(timeout=2_000):
                    await cam_btn.click()
                    await page.wait_for_timeout(300)
                    break
            except (PWTimeout, Exception):
                pass

        # Step 5: click 'Join now' or 'Ask to join' — use flexible matching
        joined = False

        # Try text-based locator first (most reliable, bypasses aria-label issues)
        for btn_text in ["Join now", "Ask to join", "Join"]:
            try:
                btn = page.locator(f"button:has-text('{btn_text}')").first
                await btn.wait_for(state="visible", timeout=8_000)
                print(f"[meet-bot] Clicking join button: {btn_text}", file=sys.stderr)
                await btn.click(force=True)
                joined = True
                break
            except (PWTimeout, Exception) as ex:
                print(f"[meet-bot] Button not found via text: {btn_text} — {ex}", file=sys.stderr)
                continue

        await self._screenshot(page, "04_after_join_click")

        if not joined:
            print("[meet-bot] No standard join button found — trying fallback", file=sys.stderr)
            try:
                await page.get_by_text("Join", exact=False).first.click(force=True)
                joined = True
            except Exception as ex:
                print(f"[meet-bot] Fallback also failed: {ex}", file=sys.stderr)

        if joined:
            print("[meet-bot] Join button clicked — waiting for admission", file=sys.stderr)
            await page.wait_for_timeout(2_000)
            await self._screenshot(page, "05_after_join_wait")

    # ─── Admission wait ────────────────────────────────────────────────────

    async def _wait_admitted(self, page: Page):
        """
        Poll until Google Meet's in-call UI is visible.
        Uses multiple detection strategies since Meet's DOM changes frequently.
        """
        await self.api.update_status("lobby")
        deadline = time.time() + self.lobby_timeout
        poll = 0
        while time.time() < deadline:
            poll += 1

            # 1. Leave call button (aria-label, exact and partial)
            for label in ["Leave call", "Leave", "End call"]:
                try:
                    btn = page.get_by_role("button", name=label)
                    if await btn.is_visible(timeout=1_500):
                        print(f"[meet-bot] Admitted — found button '{label}'", file=sys.stderr)
                        return
                except Exception:
                    pass

            # 2. Microphone toggle — only visible once inside the call
            for label in ["Turn off microphone", "Turn on microphone",
                          "Mute microphone", "Unmute microphone",
                          "microphone", "Microphone"]:
                try:
                    btn = page.get_by_role("button", name=label)
                    if await btn.is_visible(timeout=1_500):
                        print(f"[meet-bot] Admitted — found mic button '{label}'", file=sys.stderr)
                        return
                except Exception:
                    pass

            # 3. CSS selector for the red leave-call button (phone icon)
            for sel in [
                "button[aria-label*='Leave']",
                "button[aria-label*='leave']",
                "button[data-tooltip*='Leave']",
                "[jsname='CQylAd']",   # leave button jsname in some Meet versions
                "button[jsaction*='leave']",
            ]:
                try:
                    el = page.locator(sel).first
                    if await el.is_visible(timeout=1_000):
                        print(f"[meet-bot] Admitted — CSS selector hit: {sel}", file=sys.stderr)
                        return
                except Exception:
                    pass

            # 4. "Ask to join" button disappeared = we got in (or kicked)
            try:
                ask = page.locator("button:has-text('Ask to join')").first
                still_asking = await ask.is_visible(timeout=1_000)
                if not still_asking:
                    # Double-check we're on the meet URL (not an error page)
                    if "meet.google.com" in page.url:
                        print(f"[meet-bot] Admitted — 'Ask to join' gone; URL={page.url}", file=sys.stderr)
                        return
            except Exception:
                pass

            # 5. URL-based heuristics (pli=1 is set immediately so skip it)
            url = page.url
            if "?authuser" in url or "/u/" in url:
                if "accounts.google.com" not in url:
                    print(f"[meet-bot] Admitted — URL heuristic matched: {url}", file=sys.stderr)
                    return

            # 6. JavaScript check for Meet's internal state
            try:
                in_call = await page.evaluate("""
                    () => {
                        // Meet marks the call container with a specific role or attribute
                        const leaving = document.querySelector('[data-call-ended]');
                        if (leaving) return false;
                        const callbar = document.querySelector('[jscontroller][data-meeting-title]');
                        if (callbar) return true;
                        // Check if the join/lobby button is gone
                        const btns = Array.from(document.querySelectorAll('button'));
                        const hasJoin = btns.some(b =>
                            b.textContent.includes('Ask to join') ||
                            b.textContent.includes('Join now')
                        );
                        const hasLeave = btns.some(b =>
                            b.getAttribute('aria-label')?.toLowerCase().includes('leave') ||
                            b.textContent.toLowerCase().includes('leave call')
                        );
                        return hasLeave && !hasJoin;
                    }
                """)
                if in_call:
                    print("[meet-bot] Admitted — JS in-call check passed", file=sys.stderr)
                    return
            except Exception:
                pass

            # Debug screenshot every 5 polls (~15s)
            if poll % 5 == 0:
                await self._screenshot(page, f"wait_admitted_{poll:03d}")
                print(f"[meet-bot] Still waiting for admission... {int(deadline - time.time())}s left | URL={page.url}", file=sys.stderr)

            # Check if user clicked "Stop" in the dashboard
            if await self.api.is_cancelled():
                print("[meet-bot] Cancelled from dashboard while in lobby", file=sys.stderr)
                raise RuntimeError("Bot stopped by user")

            await asyncio.sleep(3)

        await self._screenshot(page, "wait_admitted_timeout")
        await self.api.update_status("lobby_timeout")
        raise RuntimeError(f"Bot never admitted to Meet within {self.lobby_timeout}s")

    # ─── Meeting end detection ─────────────────────────────────────────────

    async def _watch_for_end(self, page: Page, participant_first_seen: dict | None = None):
        end_texts = [
            "You've left the meeting",
            "The meeting has ended",
            "Return to home screen",
            "You left the call",
            "meeting has ended",
            "call has ended",
            "You've been removed",
            "You have been removed",
            "You were removed",
            "You've been removed from the meeting",
            "You've been removed from the call",
        ]
        alone_since: float | None = None
        poll = 0
        max_count_seen = 0
        admitted_at = time.time()
        people_panel_opened = False
        MAX_ALONE_SECONDS = 45     # leave if count drops from peak for this long
        # Re-open the people panel every ~5 min (every 37 polls × 8s ≈ 296s)
        # so long meetings don't lose names when the panel auto-closes.
        PANEL_REOPEN_EVERY = 37

        while True:
            await asyncio.sleep(8)
            poll += 1
            if page.is_closed():
                print("[meet-bot] Page closed — meeting ended", file=sys.stderr)
                return

            if await self.api.is_cancelled():
                print("[meet-bot] Cancelled from dashboard while in meeting", file=sys.stderr)
                return

            # Open the People panel on first opportunity AND periodically
            # thereafter so names stay visible in the DOM throughout long
            # meetings (Google Meet auto-closes the panel after a while).
            needs_panel = (
                (not people_panel_opened and poll >= 1)
                or (people_panel_opened and poll % PANEL_REOPEN_EVERY == 0 and not self._participants_seen)
            )
            if needs_panel:
                opened = False
                # Strategy 1: Playwright accessible-name (matches aria-label,
                # title, tooltip text, or button text content).
                try:
                    import re as _re
                    btn = page.get_by_role("button", name=_re.compile(r"people|show everyone|participant", _re.I))
                    if await btn.first.is_visible(timeout=1500):
                        await btn.first.click(timeout=2000)
                        opened = True
                        print("[meet-bot] People panel opened via accessible name", file=sys.stderr)
                except Exception as exc:
                    print(f"[meet-bot] People accessible-name click failed: {exc}", file=sys.stderr)

                # Strategy 2: data-tooltip / data-tooltip-id attributes (Meet
                # uses these instead of aria-label for the bottom control bar).
                if not opened:
                    try:
                        opened = await page.evaluate("""
                            () => {
                                const matches = (s) => /people|show everyone|participant/i.test(s || '');
                                const candidates = [
                                    ...document.querySelectorAll('button[data-tooltip], button[data-tooltip-id], button[aria-label], [role="button"][data-tooltip]'),
                                ];
                                for (const el of candidates) {
                                    if (matches(el.getAttribute('data-tooltip')) ||
                                        matches(el.getAttribute('aria-label')) ||
                                        matches(el.textContent)) {
                                        el.click();
                                        return true;
                                    }
                                }
                                // Last-ditch: any button whose textContent mentions People.
                                const btn = [...document.querySelectorAll('button,[role=button]')]
                                    .find(b => matches(b.textContent));
                                if (btn) { btn.click(); return true; }
                                return false;
                            }
                        """)
                        if opened:
                            print("[meet-bot] People panel opened via DOM tooltip search", file=sys.stderr)
                    except Exception as exc:
                        print(f"[meet-bot] People DOM tooltip search failed: {exc}", file=sys.stderr)

                # Strategy 3: keyboard shortcut Ctrl+Alt+P toggles the People panel in Meet.
                if not opened:
                    try:
                        await page.keyboard.press("Control+Alt+KeyP")
                        opened = True
                        print("[meet-bot] People panel opened via keyboard shortcut", file=sys.stderr)
                    except Exception as exc:
                        print(f"[meet-bot] People keyboard shortcut failed: {exc}", file=sys.stderr)

                people_panel_opened = True
                print(f"[meet-bot] People panel open attempt: {opened}", file=sys.stderr)
                await asyncio.sleep(2.0)

            try:
                # 1. End-of-meeting text on screen
                for txt in end_texts:
                    if await page.get_by_text(txt, exact=False).is_visible(timeout=500):
                        print(f"[meet-bot] Detected end text: '{txt}'", file=sys.stderr)
                        return

                # 2. Navigated away from Meet
                if "meet.google.com" not in page.url:
                    print(f"[meet-bot] Navigated away: {page.url}", file=sys.stderr)
                    return

                # 4. Participant count + names. Several DOM strategies are
                #    tried because Meet's class names are obfuscated.
                info = await page.evaluate("""
                    () => {
                        const out = { count: -1, names: [] };
                        // Count only VISIBLE participant tiles — hidden/ghost tiles
                        // (inactive streams, Meet's internal render cache, waiting-room
                        // overlays) inflate the number to 5-7 even in a 2-person call.
                        // offsetParent === null is the standard "display:none / hidden"
                        // check; getBoundingClientRect().width==0 catches visibility:hidden.
                        const allTiles = document.querySelectorAll('[data-participant-id]');
                        const visibleTiles = Array.from(allTiles).filter(t => {
                            if (!t.offsetParent && t.style.position !== 'fixed') return false;
                            const r = t.getBoundingClientRect();
                            return r.width > 0 && r.height > 0;
                        });
                        if (visibleTiles.length > 0) {
                            out.count = visibleTiles.length;
                        } else if (allTiles.length > 0) {
                            // Fallback: use people-panel count if tiles are all hidden
                            // (e.g. tiled view collapsed to sidebar)
                            const panel = document.querySelector('[data-participant-id]');
                            const ssrc = document.querySelectorAll('[data-ssrc]');
                            if (ssrc.length) out.count = ssrc.length;
                        }
                        const names = new Set();
                        let selfName = '';
                        // Helper: strip Meet's metadata noise from a row textContent.
                        // Cuts at "(You)", common Material Icon ligature words,
                        // and trailing button labels.
                        const cleanName = (raw) => {
                            if (!raw) return '';
                            let s = String(raw).replace(/\\s+/g, ' ').trim();
                            // Cut at the "(You)" suffix Meet shows for self.
                            const yi = s.indexOf('(You)');
                            if (yi > 0) s = s.substring(0, yi);
                            // Cut at known Material Icon ligature names that
                            // leak into textContent.
                            const ICONS = [
                                'devices', 'more_vert', 'more_horiz',
                                'mic_off', 'mic', 'videocam_off', 'videocam',
                                'present_to_all', 'push_pin', 'pin', 'remove',
                                'volume_off', 'volume_up', 'spatial_audio_off',
                            ];
                            for (const w of ICONS) {
                                const idx = s.indexOf(w);
                                if (idx > 0) s = s.substring(0, idx);
                            }
                            // Cut at trailing button labels.
                            for (const w of ['More actions', 'Pin', 'Remove']) {
                                const idx = s.indexOf(w);
                                if (idx > 0) s = s.substring(0, idx);
                            }
                            return s.trim();
                        };
                        // Strategy A: avatar <img alt="Name"> inside each tile.
                        // Explicitly skip brand/logo images — Meet places
                        // "Meet logo" img elements inside or near tiles.
                        document.querySelectorAll('[data-participant-id] img[alt]').forEach(img => {
                            if (/\blogo\b/i.test(img.alt)) return;
                            if (/^(google meet|meet|google|chrome)$/i.test(img.alt)) return;
                            const a = cleanName(img.alt);
                            if (a) names.add(a);
                        });
                        // Strategy B: data-self-name attribute (you / bot)
                        document.querySelectorAll('[data-self-name]').forEach(el => {
                            const n = cleanName(el.getAttribute('data-self-name'));
                            if (n) names.add(n);
                        });
                        // Strategy C: people panel list items.
                        // IMPORTANT: scope to the people-panel container so we
                        // don't pick up dropdown menu items (which also use
                        // [role="listitem"]) from the rest of the page.
                        const _cPanel = (
                            document.querySelector('[data-panel-id="participants"]') ||
                            document.querySelector('[aria-label*="participant" i]') ||
                            document.querySelector('[jsname*="people"], [class*="peoplePanel"], [class*="people-panel"]') ||
                            null
                        );
                        const _cItems = _cPanel
                            ? _cPanel.querySelectorAll('[role="listitem"]')
                            : document.querySelectorAll('[role="list"] [role="listitem"]');
                        _cItems.forEach(li => {
                            const raw = li.textContent || '';
                            const isSelf = raw.indexOf('(You)') >= 0;
                            let n = '';
                            // C1: avatar img alt within the row (skip logo images)
                            const img = li.querySelector('img[alt]');
                            if (img && img.alt
                                    && !/\blogo\b/i.test(img.alt)
                                    && !/^(google meet|meet|google|chrome)$/i.test(img.alt)) {
                                n = cleanName(img.alt);
                            }
                            // C2: aria-label of the row
                            if (!n) {
                                const al = li.getAttribute('aria-label');
                                if (al) n = cleanName(al.split(',')[0]);
                            }
                            // C3: clean the full textContent
                            if (!n) n = cleanName(raw);
                            if (!n || n.length < 2 || n.length > 80) return;
                            if (isSelf) selfName = n;
                            else names.add(n);
                        });
                        // Strategy D: name chips overlaid on video tiles.
                        // Google Meet renders a small nameplate at the bottom
                        // of every participant tile even when the People panel
                        // is closed. These appear as text nodes inside elements
                        // that sit directly inside a [data-participant-id] tile.
                        // We look for short text-only leaf nodes that look like
                        // names (NOT UI chrome, button labels, or toasts).
                        const _dUiWords = /\b(options|effects|backgrounds|spotlight|presenting|reaction|tile|emoji|might|others|full video)\b/i;
                        document.querySelectorAll('[data-participant-id]').forEach(tile => {
                            // Try aria-label on the tile itself first.
                            const tileLabel = tile.getAttribute('aria-label') || '';
                            if (tileLabel) {
                                const n = cleanName(tileLabel.split(',')[0]);
                                if (n && n.length >= 2 && n.length <= 80) { names.add(n); return; }
                            }
                            // Walk shallow children for short text nodes that look like names.
                            tile.querySelectorAll('*').forEach(el => {
                                if (el.children.length > 0) return; // skip non-leaf
                                const t = (el.textContent || '').trim();
                                if (t.length < 2 || t.length > 60) return;
                                // Skip icon ligatures and pure numbers.
                                if (/^[\\d\\s]+$/.test(t)) return;
                                if (/^[a-z_]+$/.test(t)) return;
                                // Skip sentence-like text (too many words → UI label/toast).
                                if (t.split(/\s+/).length > 5) return;
                                // Skip strings ending with sentence punctuation (toast messages).
                                if (/[.!?]$/.test(t)) return;
                                // Skip strings containing known Meet UI action words.
                                if (_dUiWords.test(t)) return;
                                const n = cleanName(t);
                                if (n && n.length >= 2) names.add(n);
                            });
                        });
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

                # Track participant names seen during the meeting (excluding the bot itself).
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
                    # Reject Google Meet UI strings (menu items, toasts, button
                    # aria-labels) that pass the DOM extraction but are not names.
                    if _is_meet_ui_string(n_clean):
                        print(f"[meet-bot] Skipping UI string (not a participant): {n_clean!r}", file=sys.stderr)
                        continue
                    if n_clean not in self._participants_seen:
                        self._participants_seen.add(n_clean)
                        self.participants.append(n_clean)
                        # Record first-seen timestamp for temporal track correlation.
                        if participant_first_seen is not None and n_clean not in participant_first_seen:
                            participant_first_seen[n_clean] = time.time()
                            print(
                                f"[meet-bot] Participant first seen: '{n_clean}' at t={participant_first_seen[n_clean]:.3f} "
                                f"(participant_first_seen={participant_first_seen})",
                                file=sys.stderr,
                            )
                        print(f"[meet-bot] Participant detected: {n_clean}", file=sys.stderr)
                        await self.api.update_participants(self.participants)
                        if len(self.participants) == 1:
                            await self.api.rename_speaker("Speaker", self.participants[0])

                now = time.time()
                in_meeting_for = now - admitted_at
                is_alone = False
                if self.auto_leave_when_alone and in_meeting_for >= self.min_meeting_seconds:
                    is_alone = (participant_count != -1 and participant_count <= 1)

                if is_alone:
                    if alone_since is None:
                        alone_since = now
                        print(f"[meet-bot] Participant count dropped ({participant_count}/{max_count_seen} peak), waiting {self.max_alone_seconds}s...", file=sys.stderr)
                    elif now - alone_since >= self.max_alone_seconds:
                        print(f"[meet-bot] Bot alone for {self.max_alone_seconds}s — meeting ended", file=sys.stderr)
                        return
                else:
                    if alone_since is not None:
                        print(f"[meet-bot] Count recovered ({participant_count}), resetting alone timer", file=sys.stderr)
                    alone_since = None

                if poll % 4 == 0:
                    print(f"[meet-bot] In meeting... poll={poll} count={participant_count} peak={max_count_seen} in_meeting={int(in_meeting_for)}s url={page.url}", file=sys.stderr)

            except Exception as exc:
                print(f"[meet-bot] watch_for_end error: {exc}", file=sys.stderr)


