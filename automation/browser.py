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

        # ✅ أعلام لتقليل استهلاك الذاكرة ومنع الطيحان
        args = [
            "--no-sandbox",
            "--disable-setuid-sandbox",
            "--disable-blink-features=AutomationControlled",
            "--disable-infobars",
            "--disable-dev-shm-usage",      # ✅ مهم جداً: يستعمل /tmp بدل /dev/shm
            "--disable-gpu",                # ✅ تقليل استهلاك الذاكرة
            "--disable-software-rasterizer",
            "--disable-accelerated-2d-canvas",
            "--no-zygote",
            "--single-process",            # ✅ يمنع تعدد العمليات ويقلل الذاكرة (قد يقلل الاستقرار ولكن يمنع الطيحان)
            "--js-flags=--max-old-space-size=512", # ✅ حد أقصى للذاكرة
            "--window-size=1280,720",      # ✅ تقليل حجم النافذة
            f"--user-agent={config.USER_AGENT}"
        ]

        self.context = await self.playwright.chromium.launch_persistent_context(
            user_data_dir=self.profile_dir,
            channel="chromium",
            headless=True,
            args=args,
            viewport={"width": 1280, "height": 720},
            locale="en-US",
            java_script_enabled=True,
            user_agent=config.USER_AGENT,
            timezone_id="America/New_York",
        )

        await self.context.add_init_script(STEALTH_JS)
        self.context.set_default_timeout(60000)
        self.context.set_default_navigation_timeout(120000)

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
