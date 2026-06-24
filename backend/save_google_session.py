"""
save_google_session.py — Run this on Windows (HOST machine, not inside Docker).

Usage:
    pip install playwright
    playwright install chromium
    python save_google_session.py

This opens a real Chromium window. Log in to Google manually (the script won't
type your password — Google blocks automation for sign-in).
After you see your Google home page, press ENTER in this terminal window and
the script will save your session to google_session.json.

Then inject it into the Docker volume:
    docker cp google_session.json zapper-pm-bot:/data/recordings/google_session.json

The bot will use it on the next meeting join.
"""
import asyncio
import json
import os


async def main():
    from playwright.async_api import async_playwright

    print("=" * 60)
    print("Google Session Saver for Zapper Bot")
    print("=" * 60)
    print()
    print("Opening a real browser window...")
    print("1. Sign in to Google with your meeting account")
    print("2. Complete any 2FA / phone verification if prompted")
    print("3. Once you're on the Google home page, come back here")
    print("   and press ENTER to save the session.")
    print()

    async with async_playwright() as pw:
        # Use a real (non-headless) browser so Google doesn't block it
        browser = await pw.chromium.launch(
            headless=False,
            args=["--disable-blink-features=AutomationControlled"],
        )
        ctx = await browser.new_context(
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/124.0.0.0 Safari/537.36"
            ),
            locale="en-US",
        )
        page = await ctx.new_page()
        await page.goto("https://accounts.google.com/", wait_until="networkidle")

        print("Browser opened. Sign in now...")
        input("\nPress ENTER after signing in to save the session...")

        session_path = "google_session.json"
        await ctx.storage_state(path=session_path)
        print(f"\n✅ Session saved to: {os.path.abspath(session_path)}")
        print()
        print("Now copy it into the Docker container:")
        print(f'  docker cp {session_path} zapper-pm-bot:/data/recordings/google_session.json')
        print()
        print("The bot will use this session on the next recording.")

        await browser.close()


if __name__ == "__main__":
    asyncio.run(main())
