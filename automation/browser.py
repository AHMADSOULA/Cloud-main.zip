import os
from playwright.async_api import async_playwright
from config import config
from automation.stealth import STEALTH_JS
from utils.logger import get_logger

log = get_logger("Browser")


class StealthBrowser:
    def __init__(self):
        self.playwright = None
        self.context = None

    async def start(self):
        self.playwright = await async_playwright().start()
        os.makedirs(config.CHROME_PROFILE_DIR, exist_ok=True)

        args = [
            "--disable-blink-features=AutomationControlled",
            "--no-sandbox",
            "--disable-setuid-sandbox",
            "--disable-dev-shm-usage",
            "--disable-gpu",
            "--disable-software-rasterizer",
            "--disable-accelerated-2d-canvas",
            "--no-first-run",
            "--no-default-browser-check",
            "--disable-infobars",
            "--disable-extensions",
            "--disable-plugins",
            "--disable-sync",
            "--disable-translate",
            "--disable-default-apps",
            "--disable-background-timer-throttling",
            "--disable-renderer-backgrounding",
            "--disable-backgrounding-occluded-windows",
            "--mute-audio",
            "--hide-scrollbars",
            "--metrics-recording-only",
            "--safebrowsing-disable-auto-update",
            "--renderer-process-limit=1",
            "--js-flags=--max-old-space-size=256",
            "--window-size=1280,720",
            f"--user-agent={config.USER_AGENT}",
        ]

        self.context = await self.playwright.chromium.launch_persistent_context(
            user_data_dir=config.CHROME_PROFILE_DIR,
            headless=config.HEADLESS,
            args=args,
            viewport={"width": 1280, "height": 720},
            user_agent=config.USER_AGENT,
            locale="en-US",
            timezone_id="America/New_York",
            color_scheme="light",
            java_script_enabled=True,
            extra_http_headers={
                "Accept-Language": "en-US,en;q=0.9",
            },
        )

        await self.context.add_init_script(STEALTH_JS)

        self.context.set_default_timeout(config.PAGE_TIMEOUT)
        self.context.set_default_navigation_timeout(config.NAV_TIMEOUT)

        log.info("✅ المتصفح جاهز")
        return self.context

    async def close(self):
        if self.context:
            try:
                await self.context.close()
            except Exception:
                pass
        if self.playwright:
            try:
                await self.playwright.stop()
            except Exception:
                pass
        log.info("تم إغلاق المتصفح")
