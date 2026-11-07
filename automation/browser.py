import os
import tempfile
import shutil
from playwright.async_api import async_playwright
from config import config
from automation.stealth import STEALTH_JS
from utils.logger import get_logger

log = get_logger("Browser")

class StealthBrowser:
    def __init__(self):
        self.playwright = None
        self.context = None
        self.profile_dir = None

    async def start(self):
        self.playwright = await async_playwright().start()
        
        self.profile_dir = tempfile.mkdtemp(prefix="chrome_profile_")
        log.info(f"📁 Using fresh profile: {self.profile_dir}")

        # ✅ نفس الأوامر ديال GC.py بالضبط
        args = [
            "--no-sandbox",
            "--disable-setuid-sandbox",
            "--disable-blink-features=AutomationControlled",
            "--disable-infobars",
            "--window-size=1920,1080",
            "--disable-dev-shm-usage"
        ]

        self.context = await self.playwright.chromium.launch_persistent_context(
            user_data_dir=self.profile_dir,
            channel="chromium",
            headless=True,
            args=args,
            viewport={"width": 1920, "height": 1080},
            locale="en-US",
            java_script_enabled=True,
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
        
        if self.profile_dir and os.path.exists(self.profile_dir):
            try:
                shutil.rmtree(self.profile_dir, ignore_errors=True)
            except Exception:
                pass
