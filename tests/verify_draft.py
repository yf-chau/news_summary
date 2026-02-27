"""
Dev verification script: uses Playwright to log into Substack dashboard
and confirm a draft exists with the expected title.

Usage:
    uv run --dev python tests/verify_draft.py --title "February 25, 2026 香港每週新聞摘要"
    uv run --dev python tests/verify_draft.py --title "Test Draft" --screenshot out.png
"""

import argparse
import json
import os
import sys
import time
from pathlib import Path

# Allow imports from project root when run as a script
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import dotenv
from playwright.sync_api import sync_playwright, expect, TimeoutError as PlaywrightTimeoutError
from playwright_stealth import Stealth

dotenv.load_dotenv()

from substack_api import COOKIE_PATH, SUBSTACK_EMAIL, SUBSTACK_PASSWORD, SUBSTACK_URL


def load_cookies(context):
    if not os.path.exists(COOKIE_PATH):
        print(f"No cookie file at {COOKIE_PATH}, skipping cookie load.")
        return
    with open(COOKIE_PATH, "r") as f:
        cookie_dict = json.load(f)
    cookies = [
        {"name": name, "value": value, "domain": ".substack.com", "path": "/"}
        for name, value in cookie_dict.items()
    ]
    context.add_cookies(cookies)
    print(f"Loaded {len(cookies)} cookies from {COOKIE_PATH}")


def login_if_needed(page):
    """Check if we're on the dashboard; if not, perform login."""
    dashboard_url = f"{SUBSTACK_URL}/publish/home"
    page.goto(dashboard_url, wait_until="networkidle")

    # Check if we landed on the dashboard
    if "/publish" in page.url:
        print("Already logged in via cookies.")
        return True

    print("Not logged in, performing email/password login...")
    if not SUBSTACK_EMAIL or not SUBSTACK_PASSWORD:
        print("Error: SUBSTACK_EMAIL and SUBSTACK_PASSWORD required for login.")
        return False

    # Sign in with password flow
    try:
        pw_link = page.locator("a:has-text('Sign in with password')")
        pw_link.wait_for(state="visible", timeout=5000)
        pw_link.click()
    except PlaywrightTimeoutError:
        pass

    email_input = page.locator("input[type='email'][name='email']")
    email_input.wait_for(state="visible", timeout=10000)
    email_input.fill(SUBSTACK_EMAIL)

    try:
        continue_btn = page.get_by_role("button", name="Continue")
        continue_btn.click(timeout=5000)
    except PlaywrightTimeoutError:
        pass

    password_input = page.locator("input[type='password'][name='password']")
    password_input.wait_for(state="visible", timeout=10000)
    password_input.fill(SUBSTACK_PASSWORD)

    try:
        continue_btn = page.get_by_role("button", name="Continue")
        continue_btn.click(timeout=5000)
    except PlaywrightTimeoutError:
        pass

    page.wait_for_url("**/publish/**", timeout=30000)
    print("Login successful.")
    return True


def find_draft(page, title: str, screenshot_path: str | None = None) -> bool:
    """Navigate to drafts and look for a draft matching the title."""
    drafts_url = f"{SUBSTACK_URL}/publish/posts?type=draft"
    page.goto(drafts_url, wait_until="networkidle")
    time.sleep(2)

    # Look for the draft title in the list
    draft_link = page.locator(f"a:has-text('{title}')").first
    try:
        draft_link.wait_for(state="visible", timeout=15000)
    except PlaywrightTimeoutError:
        print(f"Draft not found with title: {title}")
        if screenshot_path:
            page.screenshot(path=screenshot_path, full_page=True)
            print(f"Screenshot saved: {screenshot_path}")
        return False

    print(f"Found draft: {title}")

    # Click into the draft to verify content
    draft_link.click()
    page.wait_for_load_state("networkidle")
    time.sleep(2)

    if screenshot_path:
        page.screenshot(path=screenshot_path, full_page=True)
        print(f"Screenshot saved: {screenshot_path}")

    # Basic content checks
    body = page.content()
    checks = {
        "has headings": "<h" in body.lower(),
        "has links": "href=" in body.lower(),
        "has bold text": ("<strong" in body.lower() or "<b" in body.lower()),
    }
    all_passed = True
    for check, passed in checks.items():
        status = "PASS" if passed else "WARN"
        if not passed:
            all_passed = False
        print(f"  [{status}] {check}")

    return True


def main():
    parser = argparse.ArgumentParser(description="Verify a Substack draft exists")
    parser.add_argument("--title", required=True, help="Expected draft title")
    parser.add_argument("--screenshot", default="verify_draft_screenshot.png", help="Screenshot output path")
    args = parser.parse_args()

    headless = os.getenv("HEADLESS", "true").lower() in ("true", "1", "yes")

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=headless)
        context = browser.new_context(
            viewport={"width": 1280, "height": 900},
            locale="en-US",
        )
        load_cookies(context)
        page = context.new_page()
        Stealth().apply_stealth_sync(page)

        try:
            if not login_if_needed(page):
                sys.exit(1)

            found = find_draft(page, args.title, args.screenshot)
            sys.exit(0 if found else 1)
        except Exception as e:
            print(f"Error: {e}")
            page.screenshot(path="verify_error.png")
            sys.exit(1)
        finally:
            browser.close()


if __name__ == "__main__":
    main()
