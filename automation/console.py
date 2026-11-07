import asyncio
from utils.logger import get_logger

log = get_logger("Console")

class CloudConsole:
    def __init__(self, context):
        self.context = context

    async def step1_welcome_screen(self, page):
        log.info("🚀 step1: TOS الأولى")
        try:
            await page.wait_for_load_state("networkidle", timeout=10000)
            await page.wait_for_timeout(2000)    
            await page.keyboard.press("Enter")
            try:
                button = page.locator("text='I understand'")
                if await button.is_visible(timeout=3000):
                    await button.click()
            except: pass
            await page.wait_for_load_state("networkidle", timeout=10000)
        except Exception as e:
            log.warning(f"⚠️ step1: {e}")

    async def step2_tos_and_country(self, page):
        log.info("🚀 step2: Terms Dialog")
        agree_btn = page.get_by_role("button", name="Agree and continue")
        try:
            await agree_btn.wait_for(state="visible", timeout=5000)
            
            checkboxes = page.get_by_role("checkbox")
            try:
                await checkboxes.nth(0).click()
                await asyncio.sleep(1)
                await checkboxes.nth(1).click()
            except: pass
            
            await agree_btn.click()
            await page.wait_for_load_state("domcontentloaded", timeout=10000)
        except Exception:
            log.info("ℹ️ الشروط مابانوش (الحساب ديجا مقبول)، كنتجاوزوهم.")
