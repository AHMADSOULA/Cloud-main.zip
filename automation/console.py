import asyncio
import os
from playwright.async_api import expect
from utils.logger import get_logger

log = get_logger("Console")

class CloudConsole:
    def __init__(self, context, sender=None, user_tag=None):
        self.context = context
        self.sender = sender
        self.user_tag = user_tag or "@user"

    async def _shot(self, page, caption: str = ""):
        if not self.sender: return
        try:
            if not page or page.is_closed(): return
            path = f"/tmp/shot_{int(asyncio.get_event_loop().time()*1000)}.jpg"
            await page.screenshot(path=path, full_page=False, type="jpeg", quality=60, timeout=5000) 
            with open(path, "rb") as f:
                try:
                    bot = self.sender.get_bot()
                    await bot.send_photo(chat_id=self.sender.chat_id, photo=f, caption=caption[:1000] if caption else "")
                except Exception as e:
                    log.warning(f"⚠️ فشل إرسال الصورة: {e}")
            try: os.remove(path)
            except: pass
        except Exception as e:
            log.warning(f"⚠️ فشل التصوير: {e}")

    async def step1_welcome_screen(self, page):
        log.info("🚀 step1: TOS")
        try:
            await page.wait_for_load_state("networkidle")
            await page.wait_for_timeout(2000)    
            await page.keyboard.press("Enter")
            try:
                button = page.locator("text='I understand'")
                if await button.is_visible(timeout=3000):
                    await button.click()
            except: pass
            await page.wait_for_load_state("networkidle")
        except Exception as e:
            log.warning(f"⚠️ step1: {e}")

    async def step2_tos_and_country(self, page):
        log.info("🚀 step2: Terms Dialog")
        agree_btn = page.get_by_role("button", name="Agree and continue")
        try:
            await agree_btn.wait_for(state="visible", timeout=10000)
            checkboxes = page.get_by_role("checkbox")
            await checkboxes.nth(0).click()
            await asyncio.sleep(1)
            await checkboxes.nth(1).click()
            await agree_btn.click()
            await page.wait_for_load_state("domcontentloaded")
        except Exception:
            log.info("ℹ️ الشروط مابانوش، تخطي تلقائي.")

    async def step3_enable_api(self, page, project_id, authuser):
        log.info("🚀 step3: Enable API")
        api_url = f"https://console.cloud.google.com/apis/library/run.googleapis.com?project={project_id}&authuser={authuser}"
        await page.goto(api_url, wait_until="domcontentloaded", timeout=60000)
        
        enable_btn = page.get_by_role("button", name="Enable")
        manage_btn = page.get_by_role("button", name="Manage")
        disable_btn = page.get_by_text("Disable API") 
        
        try:
            await expect(enable_btn.or_(manage_btn)).to_be_visible(timeout=15000)
            if await enable_btn.is_visible():
                await enable_btn.click()
                await expect(manage_btn.or_(disable_btn)).to_be_visible(timeout=60000)
            elif await manage_btn.is_visible():
                pass 
        except Exception as e:
             raise Exception(f"عطل في إيجاد زر تفعيل الـ API: {str(e)}")

    async def step4_create_cloud_run(self, page, project_id, authuser, image, region="europe-west1"):
        log.info(f"🌐 step4: إنشاء Cloud Run — region={region}")
        run_url = f"https://console.cloud.google.com/run/create?project={project_id}&authuser={authuser}&region={region}"
        await page.goto(run_url, wait_until="domcontentloaded", timeout=60000)
        
        await page.wait_for_timeout(5000)
        
        try:
            label = page.get_by_text("Container Image URL").first
            await label.click(timeout=10000)
            await page.wait_for_timeout(500)
            await page.keyboard.type(image, delay=50)
        except Exception as e:
            raise Exception(f"فشل في الضغط وكتابة الرابط: {str(e)}")
        
        await page.wait_for_timeout(3000)
        
        try:
            await page.get_by_role("radio", name="Allow public access").click(timeout=10000)
            await page.get_by_role("radio", name="Instance-based").click(timeout=10000)
            
            try:
                await page.get_by_role("button", name="Hide").click(timeout=2000)
            except: pass
                
            await page.keyboard.press("End")
            await page.wait_for_timeout(1000)
            
            create_btn = page.get_by_role("button", name="Create")
            await create_btn.click(force=True, timeout=10000)
        except Exception as e:
            raise Exception(f"فشل في اختيار الإعدادات أو ضغط Create: {str(e)}")

    async def step5_get_deployed_url(self, page):
        log.info("⏳ step5: انتظار الرابط")
        try:
            link_locator = page.locator('a[href*="run.app"]')
            await link_locator.wait_for(state="visible", timeout=120000) 
            return await link_locator.get_attribute("href")
        except Exception as e:
            raise Exception(f"ما لقيناش رابط run.app: {str(e)}")
