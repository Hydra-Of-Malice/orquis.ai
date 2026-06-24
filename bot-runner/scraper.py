"""
Scrapes Teams DOM roster for participant names every 30 seconds.
Includes fallback selectors and alerting when the roster is visible
but yields zero names (broken selector situation).
"""
import asyncio
import sys
from typing import Callable

# Ordered list of fallback selector pairs (roster_open_btn, name_elements).
# Microsoft rotates data-tid values frequently; these cover several known
# variants so a single broken selector doesn't silence name capture silently.
_ROSTER_BUTTON_FALLBACKS = [
    "[data-tid='roster-button']",
    "[data-tip='People']",
    "button[aria-label='People']",
    "button[aria-label*='participant']",
    "[aria-label='Show participants']",
]

_NAME_ELEMENT_FALLBACKS = [
    "[data-tid='roster-participant'] [data-tid='participant-display-name']",
    "[data-tid='roster-participant'] span[class*='name']",
    "[class*='roster'] [class*='participantDisplayName']",
    "[class*='participants-list'] [class*='name']",
    "li[class*='participant'] span[class*='name']",
    "[aria-label*='participant'] [class*='name']",
]

_KNOWN_BOT_NAMES = {"zapper recorder", "recording bot", "zapper"}


class ParticipantScraper:
    def __init__(self, page, selectors: dict):
        self.page = page
        self.sel = selectors
        self._zero_name_count_streak = 0

    async def watch(self, on_update: Callable[[list[str]], None]):
        while True:
            try:
                names = await self._scrape_names()
                if names:
                    self._zero_name_count_streak = 0
                    on_update(names)
                else:
                    self._zero_name_count_streak += 1
                    if self._zero_name_count_streak == 3:
                        # 3 consecutive empty results — warn so the logs are
                        # actionable; don't spam after that.
                        await self._warn_empty_roster()
            except Exception as e:
                print(f"[scraper] Error during roster scrape: {e}", file=sys.stderr)
            await asyncio.sleep(30)

    async def _warn_empty_roster(self):
        """Check whether there are *any* elements in the roster panel.
        If yes, the selectors are broken; emit a loud warning."""
        try:
            # A very broad heuristic: any <li> or participant-like element.
            count = await self.page.locator(
                "[class*='roster'] li, [class*='participant'], [data-tid*='participant']"
            ).count()
            if count > 0:
                print(
                    f"[scraper] WARNING: roster panel has ~{count} element(s) but all "
                    "name selectors returned empty strings. "
                    "Microsoft may have changed the DOM — update selectors.yaml.",
                    file=sys.stderr,
                )
            else:
                print(
                    "[scraper] Roster appears empty or panel is not open — no names available.",
                    file=sys.stderr,
                )
        except Exception as exc:
            print(f"[scraper] Could not count roster elements: {exc}", file=sys.stderr)

    async def _scrape_names(self) -> list[str]:
        # Check if the roster panel container exists in the DOM. If yes, it's open!
        roster_already_open = False
        try:
            panel_exists = await self.page.evaluate("""
                () => !!document.querySelector('[data-tid="roster-view"], [data-tid="roster-panel"], [class*="roster"], [class*="people-pane"], [class*="peoplePane"], #roster-panel')
            """)
            if panel_exists:
                roster_already_open = True
        except Exception:
            pass

        # Fallback visibility check on elements
        if not roster_already_open:
            custom_sel = self.sel.get("participant_names")
            all_selectors = (
                ([custom_sel] if custom_sel else []) + _NAME_ELEMENT_FALLBACKS
            )
            for sel in all_selectors:
                try:
                    if await self.page.locator(sel).first.is_visible(timeout=200):
                        roster_already_open = True
                        break
                except Exception:
                    pass

        if not roster_already_open:
            # Try to open the roster panel using any known button selector.
            for btn_sel in [self.sel.get("roster_button")] + _ROSTER_BUTTON_FALLBACKS:
                if not btn_sel:
                    continue
                try:
                    roster_btn = self.page.locator(btn_sel)
                    if await roster_btn.is_visible(timeout=1500):
                        await roster_btn.click()
                        await asyncio.sleep(1.0)
                        break
                except Exception:
                    continue

        # Extract names using JS evaluation for maximum resilience
        try:
            names = await self.page.evaluate("""
                () => {
                    const panel = document.querySelector('[data-tid="roster-view"], [data-tid="roster-panel"], [class*="roster"], [class*="people-pane"], [class*="peoplePane"], #roster-panel');
                    if (!panel) return [];
                    const rows = panel.querySelectorAll('[data-tid*="participant"], [class*="participant"], [role="listitem"], [role="treeitem"], li');
                    const found = new Set();
                    const clean = (s) => (s || '')
                        .replace(/\\s+/g, ' ')
                        .replace(/\\(You\\)/i, '')
                        .replace(/\\(Guest\\)/i, '')
                        .replace(/Organizer/gi, '')
                        .replace(/Muted|Unmuted|Camera (on|off)/gi, '')
                        .trim();
                    for (const row of rows) {
                        let n = '';
                        const dn = row.querySelector('[data-tid="participant-display-name"], [data-tid*="display-name"], [class*="name"]');
                        if (dn) n = clean(dn.textContent);
                        if (!n) {
                            const al = row.getAttribute('aria-label');
                            if (al) n = clean(al.split(',')[0]);
                        }
                        if (!n) n = clean(row.textContent);
                        if (n && n.length >= 2 && n.length <= 80) {
                            found.add(n);
                        }
                    }
                    return [...found];
                }
            """)
            if names:
                return [n for n in names if n.lower() not in _KNOWN_BOT_NAMES]
        except Exception as e:
            print(f"[scraper] JS name extraction failed: {e}", file=sys.stderr)

        # Fallback to standard selector locator approach
        custom_sel = self.sel.get("participant_names")
        all_selectors = (
            ([custom_sel] if custom_sel else []) + _NAME_ELEMENT_FALLBACKS
        )
        for sel in all_selectors:
            try:
                elements = await self.page.locator(sel).all()
                names = []
                for el in elements:
                    try:
                        name = (await el.inner_text()).strip()
                    except Exception:
                        name = ""
                    if name and name.lower() not in _KNOWN_BOT_NAMES:
                        names.append(name)
                if names:
                    return names
            except Exception:
                continue

        return []
