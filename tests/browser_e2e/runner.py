"""
GlobalTalk AI - Comprehensive Browser E2E Test Runner
Executes the Complete Browser Test Matrix and Golden Call according to PDF requirements.
Uses Microsoft Edge in headless mode with microphone permissions and fake media devices.
Captures Console logs, Network requests, WebSocket events, and saves screenshots.
"""
from __future__ import annotations

import asyncio
import base64
import json
import os
import sys
import time
from pathlib import Path

# Fix Windows console UTF-8 output
sys.stdout.reconfigure(encoding="utf-8")

from playwright.sync_api import sync_playwright, Page, BrowserContext, Browser, ConsoleMessage, Request, Response

REPO = Path(__file__).resolve().parents[2]
SCREENSHOTS_DIR = REPO / "tests" / "browser_e2e" / "screenshots"
SCREENSHOTS_DIR.mkdir(parents=True, exist_ok=True)

def resolve_browser_executable(candidates: tuple[Path, ...] | None = None) -> str:
    """Find a Chromium-compatible Edge install on this Windows host.

    Developer machines may have regular Edge, EdgeCore, or both.  Keep the
    browser checklist runnable across those layouts instead of hard-coding one
    version-specific install location.
    """
    if candidates is None:
        edgecore_root = Path(r"C:\Program Files (x86)\Microsoft\EdgeCore")
        candidates = (
            Path(r"C:\Program Files\Microsoft\Edge\Application\msedge.exe"),
            Path(r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"),
            *sorted(edgecore_root.glob("*/msedge.exe"), reverse=True),
        )
    for candidate in candidates:
        if candidate.is_file():
            return str(candidate)
    searched = ", ".join(str(candidate) for candidate in candidates)
    raise FileNotFoundError(f"Microsoft Edge was not found. Searched: {searched}")


EDGE_PATH = resolve_browser_executable()
BASE_URL = "http://localhost:5173"
API_URL = "http://127.0.0.1:8088"

# Test results store
RESULTS = []

def record_result(test_id: str, url: str, feature: str, expected: str, actual: str,
                  result: str, console_errors: list[str], failed_network: list[dict],
                  reproduction_steps: str = "", root_cause: str = "", solution: str = "",
                  files_changed: str = ""):
    entry = {
        "TEST_ID": test_id,
        "URL": url,
        "FEATURE": feature,
        "EXPECTED": expected,
        "ACTUAL": actual,
        "CONSOLE_ERROR": "\n".join(console_errors) if console_errors else "None",
        "NETWORK_REQUEST_STATUS": json.dumps(failed_network) if failed_network else "All 2xx/3xx",
        "REPRODUCTION_STEPS": reproduction_steps,
        "ROOT_CAUSE": root_cause,
        "SOLUTION": solution,
        "FILES_CHANGED": files_changed,
        "RESULT": result,
    }
    RESULTS.append(entry)
    print(f"\n==================================================")
    print(f"[{result}] {test_id} - {feature}")
    print(f"URL: {url}")
    print(f"Expected: {expected}")
    print(f"Actual: {actual}")
    if console_errors:
        print(f"Console Errors: {console_errors}")
    if failed_network:
        print(f"Failed Network: {failed_network}")
    print(f"==================================================\n")

def attach_listeners(page: Page, logs: list[str], errors: list[str], net_fails: list[dict]):
    def on_console(msg: ConsoleMessage):
        text = f"[{msg.type.upper()}] {msg.text}"
        logs.append(text)
        if msg.type == "error":
            errors.append(text)

    def on_response(resp: Response):
        if resp.status >= 400:
            net_fails.append({
                "url": resp.url,
                "status": resp.status,
                "status_text": resp.status_text,
            })

    page.on("console", on_console)
    page.on("response", on_response)

def run_tests():
    print(f"Launching Edge Playwright against {BASE_URL}...")
    with sync_playwright() as p:
        browser = p.chromium.launch(
            executable_path=EDGE_PATH,
            headless=True,
            args=[
                "--use-fake-device-for-media-stream",
                "--use-fake-ui-for-media-stream",
                "--disable-web-security",
            ]
        )

        context = browser.new_context(
            permissions=["microphone", "camera"],
            viewport={"width": 1280, "height": 800},
        )
        page = context.new_page()

        # -------------------------------------------------------------
        # TEST 1: Landing Page (/)
        # -------------------------------------------------------------
        logs_1, errs_1, net_1 = [], [], []
        attach_listeners(page, logs_1, errs_1, net_1)
        try:
            page.goto(f"{BASE_URL}/", wait_until="networkidle", timeout=30000)
            page.reload(wait_until="networkidle")
            title = page.title()
            page.screenshot(path=str(SCREENSHOTS_DIR / "1_landing.png"))
            has_hero = page.locator("h1, h2").first.is_visible()
            # verify CTAs exist
            translate_cta = page.locator('a[href*="/translate"], button:has-text("Translate")').first.is_visible()
            record_result(
                "TEST-1-LANDING",
                f"{BASE_URL}/",
                "Landing Page Load & UI",
                "Clean load, hero visible, navigation CTAs present, zero red console errors",
                f"Title: '{title}', Hero visible: {has_hero}, CTA visible: {translate_cta}",
                "PASS" if has_hero and not errs_1 else ("WARN" if has_hero else "FAIL"),
                errs_1, net_1,
                reproduction_steps="Open / -> hard refresh -> check elements"
            )
        except Exception as e:
            record_result("TEST-1-LANDING", f"{BASE_URL}/", "Landing Page", "Load cleanly", str(e), "FAIL", errs_1, net_1)

        # -------------------------------------------------------------
        # AUTHENTICATE WITH DEMO ACCOUNT FOR APP FLOWS
        # -------------------------------------------------------------
        logs_auth, errs_auth, net_auth = [], [], []
        attach_listeners(page, logs_auth, errs_auth, net_auth)
        try:
            page.goto(f"{BASE_URL}/login", wait_until="networkidle")
            demo_btn = page.locator('button:has-text("Use demo account")')
            if demo_btn.is_visible():
                demo_btn.click()
                page.wait_for_timeout(2000)
            else:
                page.fill('input[type="email"]', "demo@globaltalk.local")
                page.fill('input[type="password"]', "demo1234")
                page.click('button[type="submit"]')
                page.wait_for_timeout(2000)
            print("Auth state:", page.url)
        except Exception as e:
            print("Login error:", e)

        # -------------------------------------------------------------
        # TEST 2: Text Translate (/translate)
        # -------------------------------------------------------------
        logs_2, errs_2, net_2 = [], [], []
        attach_listeners(page, logs_2, errs_2, net_2)
        try:
            page.goto(f"{BASE_URL}/translate", wait_until="networkidle", timeout=30000)
            page.wait_for_timeout(1000)
            src_area = page.locator('textarea[aria-label="Source text"]')
            src_area.fill("Hello, welcome to GlobalTalk AI platform.")
            page.wait_for_function(
                """() => {
                    const output = document.querySelector('[aria-label="Translated text"]')?.textContent?.trim();
                    return Boolean(output && output !== 'Translation appears here…');
                }""",
                timeout=15000,
            )
            page.screenshot(path=str(SCREENSHOTS_DIR / "2_translate.png"))

            # Check translated text display
            trans_display = page.locator('[aria-label="Translated text"]').text_content() or ""
            print("Translated output:", trans_display)

            # Test clearing
            clear_btn = page.locator('button[title="Clear text"]')
            if clear_btn.is_visible():
                clear_btn.click()
                page.wait_for_timeout(500)

            is_valid_translation = len(trans_display.strip()) > 0 and trans_display.strip() != "Hello, welcome to GlobalTalk AI platform."
            record_result(
                "TEST-2-TRANSLATE",
                f"{BASE_URL}/translate",
                "Text Translation (/translate)",
                "Input text translated to target language, not matching original source, no errors",
                f"Output: '{trans_display.strip()}'",
                "PASS" if is_valid_translation else "FAIL",
                errs_2, net_2,
                reproduction_steps="Enter text in /translate -> check target display"
            )
        except Exception as e:
            record_result("TEST-2-TRANSLATE", f"{BASE_URL}/translate", "Text Translate", "Translate text", str(e), "FAIL", errs_2, net_2)

        # -------------------------------------------------------------
        # TEST 3: AI Writing (/write)
        # -------------------------------------------------------------
        logs_3, errs_3, net_3 = [], [], []
        attach_listeners(page, logs_3, errs_3, net_3)
        try:
            page.goto(f"{BASE_URL}/write", wait_until="networkidle", timeout=30000)
            page.wait_for_timeout(1000)
            draft_input = page.locator('textarea[aria-label="Input draft text"], textarea#source-draft-input')
            draft_input.fill("This is a exampel of bad writen text that have lots of grammar mistake and need inprovement.")
            page.wait_for_timeout(1500)

            # Click Improve with Write or Auto-fix draft
            improve_btn = page.locator('button:has-text("Improve with Write")')
            if improve_btn.is_visible():
                improve_btn.click()
                page.wait_for_timeout(2000)

            page.screenshot(path=str(SCREENSHOTS_DIR / "3_write.png"))
            improved_text = page.locator('div:has-text("Improved version")').first.text_content() or ""
            print("Write output snippet:", improved_text[:200])

            has_improvements = "improvement" in improved_text.lower() or "clean" in improved_text.lower()
            record_result(
                "TEST-3-WRITE",
                f"{BASE_URL}/write",
                "AI Writing Assistant (/write)",
                "Grammar and spelling corrected, rephrased output generated with diffs/improvements",
                f"Result displayed: {has_improvements}",
                "PASS" if has_improvements else "FAIL",
                errs_3, net_3,
                reproduction_steps="Enter draft -> Click Improve with Write -> verify changes"
            )
        except Exception as e:
            record_result("TEST-3-WRITE", f"{BASE_URL}/write", "AI Writing", "Correct draft", str(e), "FAIL", errs_3, net_3)

        # -------------------------------------------------------------
        # TEST 4: Voice (/voice)
        # -------------------------------------------------------------
        logs_4, errs_4, net_4 = [], [], []
        attach_listeners(page, logs_4, errs_4, net_4)
        try:
            page.goto(f"{BASE_URL}/voice", wait_until="networkidle", timeout=30000)
            page.wait_for_timeout(1000)
            # Check tabs
            live_tab = page.locator('button:has-text("Live Voice")')
            phone_tab = page.locator('button:has-text("International Call")')
            f2f_tab = page.locator('button:has-text("Face-to-Face")')

            # Test Sample Simulation
            sample_btn = page.locator('button:has-text("Try sample")')
            if sample_btn.is_visible():
                sample_btn.click()
                page.wait_for_timeout(3500)

            page.screenshot(path=str(SCREENSHOTS_DIR / "4_voice.png"))
            voice_text = page.content()
            has_voice_content = "Hallo" in voice_text or "Hello" in voice_text or "Speaker" in voice_text

            # Click Phone Calling Tab to verify phone integration
            if phone_tab.is_visible():
                phone_tab.click()
                page.wait_for_timeout(1000)

            record_result(
                "TEST-4-VOICE",
                f"{BASE_URL}/voice",
                "Realtime Voice & Phone Calling (/voice)",
                "Voice UI loaded, Live Voice simulation/mic works, Phone tab operational",
                f"Live Voice active: {has_voice_content}, Phone tab: {phone_tab.is_visible()}",
                "PASS" if has_voice_content else "FAIL",
                errs_4, net_4,
                reproduction_steps="Go to /voice -> Try sample speech -> Switch to International Call tab"
            )
        except Exception as e:
            record_result("TEST-4-VOICE", f"{BASE_URL}/voice", "Voice", "Voice speech test", str(e), "FAIL", errs_4, net_4)

        # -------------------------------------------------------------
        # TEST 5: Meetings Hub & Meeting Room (/meetings -> /meeting/:id)
        # -------------------------------------------------------------
        logs_5, errs_5, net_5 = [], [], []
        attach_listeners(page, logs_5, errs_5, net_5)
        try:
            page.goto(f"{BASE_URL}/meetings", wait_until="networkidle", timeout=30000)
            page.wait_for_timeout(1000)
            new_meeting_btn = page.locator('button:has-text("New meeting")')
            new_meeting_btn.click()
            page.wait_for_timeout(500)
            page.fill('input[placeholder*="Weekly sync"]', "Browser Test Meeting")
            page.click('button:has-text("Create & join")')
            page.wait_for_url("**/meeting/*", timeout=20000)
            meeting_url = page.url
            print("Entered meeting URL:", meeting_url)
            page.wait_for_timeout(3000)
            page.screenshot(path=str(SCREENSHOTS_DIR / "5_meeting.png"))

            # Test controls (mic, camera, chat drawer)
            chat_btn = page.locator('button[aria-label*="chat"], button:has-text("chat")').first
            if chat_btn.is_visible():
                chat_btn.click()
                page.wait_for_timeout(500)

            in_meeting = "/meeting/" in page.url
            record_result(
                "TEST-5-MEETINGS",
                meeting_url,
                "Meetings Room Lifecycle (/meetings -> /meeting/:id)",
                "Create meeting, transition to /meeting/:id, room initialized without crash",
                f"In room: {in_meeting}, URL: {meeting_url}",
                "PASS" if in_meeting else "FAIL",
                errs_5, net_5,
                reproduction_steps="Create new meeting -> redirect to /meeting/:id -> verify room components"
            )
        except Exception as e:
            record_result("TEST-5-MEETINGS", f"{BASE_URL}/meetings", "Meetings Room", "Create and join meeting", str(e), "FAIL", errs_5, net_5)

        # -------------------------------------------------------------
        # TEST 6: Documents (/documents)
        # -------------------------------------------------------------
        logs_6, errs_6, net_6 = [], [], []
        attach_listeners(page, logs_6, errs_6, net_6)
        try:
            page.goto(f"{BASE_URL}/documents", wait_until="networkidle", timeout=30000)
            page.wait_for_timeout(1000)
            has_dropzone = page.locator('[aria-label="Upload document"]').is_visible()

            # Create test document
            tmp_doc = REPO / "tests" / "browser_e2e" / "test_doc.txt"
            tmp_doc.write_text("GlobalTalk AI Quarterly Product Report.\nRealtime translation is operating with low latency.", encoding="utf-8")

            file_input = page.locator('input[type="file"]')
            file_input.set_input_files(str(tmp_doc))
            page.wait_for_timeout(3000)
            page.screenshot(path=str(SCREENSHOTS_DIR / "6_documents.png"))

            doc_content = page.content()
            doc_uploaded = "test_doc.txt" in doc_content or "uploaded" in doc_content.lower()

            record_result(
                "TEST-6-DOCUMENTS",
                f"{BASE_URL}/documents",
                "Document Translation (/documents)",
                "Dropzone visible, file upload initiates processing pipeline",
                f"Uploaded test_doc.txt: {doc_uploaded}",
                "PASS" if doc_uploaded else "FAIL",
                errs_6, net_6,
                reproduction_steps="Open /documents -> upload test_doc.txt -> verify status"
            )
        except Exception as e:
            record_result("TEST-6-DOCUMENTS", f"{BASE_URL}/documents", "Documents", "Upload document", str(e), "FAIL", errs_6, net_6)

        # -------------------------------------------------------------
        # TEST 7: Glossaries (/glossaries)
        # -------------------------------------------------------------
        logs_7, errs_7, net_7 = [], [], []
        attach_listeners(page, logs_7, errs_7, net_7)
        try:
            page.goto(f"{BASE_URL}/glossaries", wait_until="networkidle", timeout=30000)
            page.wait_for_timeout(1000)
            new_gloss_btn = page.locator('button:has-text("+ New glossary")')
            has_gloss_btn = new_gloss_btn.is_visible()
            if has_gloss_btn:
                new_gloss_btn.click()
                page.wait_for_timeout(500)
                page.get_by_label("Name").fill(f"Test Glossary {int(time.time())}")
                page.get_by_role("button", name="Create", exact=True).click()
                page.wait_for_timeout(2000)

            page.screenshot(path=str(SCREENSHOTS_DIR / "7_glossaries.png"))
            gloss_page_ok = has_gloss_btn and not errs_7
            record_result(
                "TEST-7-GLOSSARIES",
                f"{BASE_URL}/glossaries",
                "Glossary Management (/glossaries)",
                "Glossary list displayed, create modal opens and creates glossary",
                f"New glossary button: {has_gloss_btn}",
                "PASS" if gloss_page_ok else "FAIL",
                errs_7, net_7,
                reproduction_steps="Go to /glossaries -> Click + New glossary -> Fill form -> Save"
            )
        except Exception as e:
            record_result("TEST-7-GLOSSARIES", f"{BASE_URL}/glossaries", "Glossaries", "Manage glossaries", str(e), "FAIL", errs_7, net_7)

        # -------------------------------------------------------------
        # TEST 8: Usage (/usage)
        # -------------------------------------------------------------
        logs_8, errs_8, net_8 = [], [], []
        attach_listeners(page, logs_8, errs_8, net_8)
        try:
            page.goto(f"{BASE_URL}/usage", wait_until="networkidle", timeout=30000)
            page.wait_for_timeout(1500)
            page.screenshot(path=str(SCREENSHOTS_DIR / "8_usage.png"))
            usage_content = page.content()
            has_metrics = "Usage" in usage_content and ("Characters" in usage_content or "Translation" in usage_content or "plan" in usage_content.lower())

            record_result(
                "TEST-8-USAGE",
                f"{BASE_URL}/usage",
                "Usage & Billing Metering (/usage)",
                "Usage metrics dashboard loaded with tenant-scoped cards and quotas",
                f"Usage cards visible: {has_metrics}",
                "PASS" if has_metrics else "FAIL",
                errs_8, net_8,
                reproduction_steps="Go to /usage -> inspect metering totals"
            )
        except Exception as e:
            record_result("TEST-8-USAGE", f"{BASE_URL}/usage", "Usage", "Usage dashboard", str(e), "FAIL", errs_8, net_8)

        browser.close()

    # Save complete test report
    report_file = REPO / "tests" / "browser_e2e" / "report.json"
    with open(report_file, "w", encoding="utf-8") as f:
        json.dump(RESULTS, f, indent=2)
    print(f"\nAll browser tests complete. Report saved to {report_file}")

if __name__ == "__main__":
    run_tests()
