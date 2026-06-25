"""
Proactive meeting rules engine — evaluates every 5 seconds during a meeting.
Rules are fetched from the backend API (trigger / action / params schema).
Supported triggers: on_join, elapsed_minutes, speaker_keyword, silence_seconds, on_leave
Supported actions: speak_tts, take_note, summarise_now, post_chat, mute_self
"""
import asyncio
import time


class MeetingController:
    def __init__(self, live_transcript, recording_id, output, api):
        self.transcript = live_transcript
        self.recording_id = recording_id
        self.output = output
        self.api = api
        self.start_time = time.time()
        self.last_speech_at = time.time()
        # Per-rule cooldown tracker: {rule_id: last_fired_ts}
        self._last_fired: dict[str, float] = {}
        self._join_fired: set[str] = set()

    async def run(self):
        # Fire on_join rules once at startup
        await asyncio.sleep(3)
        await self._fire_trigger("on_join")

        while True:
            await asyncio.sleep(5)
            if await self.api.is_muted():
                continue

            now = time.time()
            elapsed_minutes = int((now - self.start_time) / 60)
            recent_text = self.transcript.get_recent(minutes=2)

            # Update last speech time from transcript activity
            last_seg = self.transcript.get_last_segment()
            if last_seg:
                self.last_speech_at = now

            rules = await self.api.get_rules()

            for rule in rules:
                if not rule.get("enabled"):
                    continue

                rule_id = str(rule.get("id", ""))
                trigger = rule.get("trigger", "")
                params = rule.get("params") or {}

                # Cooldown check (default 120s per rule)
                cooldown = float(params.get("cooldown_seconds", 120))
                last_fired = self._last_fired.get(rule_id, 0)
                if (now - last_fired) < cooldown:
                    continue

                fired = False
                speak_text = None

                # ── Trigger evaluation ────────────────────────────────────
                if trigger == "on_join":
                    if rule_id not in self._join_fired:
                        fired = True
                        self._join_fired.add(rule_id)
                        speak_text = params.get("template", "")

                elif trigger == "elapsed_minutes":
                    interval = int(params.get("minutes", 20))
                    if elapsed_minutes > 0 and elapsed_minutes % interval == 0:
                        fired = True
                        speak_text = params.get("template", "").format(
                            elapsed=elapsed_minutes
                        )

                elif trigger == "silence_seconds":
                    silence_threshold = float(params.get("seconds", 45))
                    if (now - self.last_speech_at) >= silence_threshold:
                        fired = True
                        self.last_speech_at = now
                        speak_text = params.get("template", "")

                elif trigger == "speaker_keyword":
                    keywords = params.get("keywords", [])
                    text_lower = recent_text.lower()
                    for kw in keywords:
                        if kw.lower() in text_lower:
                            fired = True
                            speak_text = params.get("template", "")
                            break

                elif trigger == "participant_count":
                    participants = await self.api.get_participants()
                    threshold = int(params.get("count", 2))
                    if len(participants) >= threshold:
                        fired = True
                        speak_text = params.get("template", "")

                if not fired:
                    continue

                # ── Action execution ─────────────────────────────────────
                action = rule.get("action", "speak_tts")
                self._last_fired[rule_id] = now

                if action == "speak_tts" and speak_text:
                    # Use LLM if template has {prompt} placeholder, else speak directly
                    if "{" in speak_text:
                        context = {
                            "live_transcript": self.transcript.get_recent(minutes=10),
                            "participants": await self.api.get_participants(),
                            **(await self.api.get_meeting_context()),
                        }
                        response = await self.api.ask_llm_proactive(speak_text, context)
                        if response and response.strip():
                            await self.output.speak(response)
                            await self.api.log_qa(speak_text, response, "proactive_rule", rule_id)
                    else:
                        await self.output.speak(speak_text)
                        await self.api.log_qa(
                            f"[rule:{rule.get('name', rule_id)}]",
                            speak_text,
                            "proactive_rule",
                            rule_id,
                        )

                elif action == "take_note":
                    # Log the matching keyword context as a Q&A note
                    note = f"[Auto-note] Keyword detected in: {recent_text[-200:]}"
                    await self.api.log_qa(
                        f"[rule:{rule.get('name', rule_id)}]",
                        note,
                        "proactive_rule",
                        rule_id,
                    )

                elif action == "summarise_now":
                    context = {"live_transcript": self.transcript.get_recent(minutes=30)}
                    summary = await self.api.ask_llm_proactive(
                        "Summarise the meeting so far in 3-5 bullet points.", context
                    )
                    if summary:
                        await self.output.speak(summary)
                        await self.api.log_qa("summarise_now", summary, "proactive_rule", rule_id)

                elif action == "mute_self":
                    await self.api.update_status("muted")

    async def _fire_trigger(self, trigger_name: str):
        rules = await self.api.get_rules()
        for rule in rules:
            if rule.get("trigger") == trigger_name and rule.get("enabled"):
                params = rule.get("params") or {}
                speak_text = params.get("template", "")
                if speak_text and rule.get("action") == "speak_tts":
                    await self.output.speak(speak_text)
