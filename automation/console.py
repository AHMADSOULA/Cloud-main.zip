import asyncio
from playwright.async_api import expect
from utils.logger import get_logger

log = get_logger("Console")

class CloudConsole:
    def __init__(self, context, sender=None, user_tag=None):
        self.context = context
        self.sender = sender
        self.user_tag = user_tag or "@user"

    async def _shot(self, page, caption: str = ""):
        if not self.sender:
            return
        try:
            path = f"/tmp/shot_{int(asyncio.get_event_loop().time()*1000)}.png"
            await page.screenshot(path=path, full_page=False, timeout=8000)
            with open(path, "rb") as f:
                try:
                    bot = self.sender.get_bot()
                    if caption:
                        await bot.send_photo(chat_id=self.sender.chat_id, photo=f, caption=caption[:1000])
                    else:
                        await bot.send_photo(chat_id=self.sender.chat_id, photo=f)
                except Exception:
                    pass
            import os
            try: os.remove(path)
            except Exception: pass
        except Exception:
            pass

    async def step1_welcome_screen(self, page):
        try:
            await page.wait_for_load_state("networkidle", timeout=10000)
        except Exception:
            pass
        await page.wait_for_timeout(1500)
        try:
            await page.keyboard.press("Enter")
        except Exception:
            pass
        try:
            button = page.locator("text='I understand'")
            if await button.is_visible(timeout=3000):
                await button.click()
        except Exception:
            pass

    async def step2_terms_dialog(self, page):
        agree_btn = page.get_by_role("button", name="Agree and continue")
        try:
            await agree_btn.wait_for(state="visible", timeout=8000)
            checkboxes = page.get_by_role("checkbox")
            try:
                cnt = await checkboxes.count()
                if cnt >= 2:
                    await checkboxes.nth(0).click()
                    await asyncio.sleep(0.5)
                    await checkboxes.nth(1).click()
                elif cnt == 1:
                    await checkboxes.nth(0).click()
            except Exception:
                pass
            await agree_btn.click()
        except Exception:
            pass

    async def step3_enable_api(self, page, project_id, authuser):
        api_url = f"https://console.cloud.google.com/apis/library/run.googleapis.com?project={project_id}&authuser={authuser}"
        await page.goto(api_url, wait_until="domcontentloaded", timeout=30000)
        await page.wait_for_timeout(2000)
        enable_btn = page.get_by_role("button", name="Enable")
        manage_btn = page.get_by_role("button", name="Manage")
        try:
            await expect(enable_btn.or_(manage_btn)).to_be_visible(timeout=10000)
            if await enable_btn.is_visible():
                await enable_btn.click()
                await page.wait_for_timeout(2000)
        except Exception:
            pass

    async def step4_create_cloud_run(self, page, project_id, authuser, image, region="us-central1"):
        run_url = f"https://console.cloud.google.com/run/create?project={project_id}&authuser={authuser}&region={region}"
        await page.goto(run_url, wait_until="domcontentloaded", timeout=60000)
        await page.wait_for_timeout(5000)

        # ✅ 1. إدخال صورة الدوكر بالطريقة الناجحة (الضغط على النص ثم الكتابة)
        try:
            label = page.get_by_text("Container Image URL").first
            await label.click(timeout=10000)
            await page.wait_for_timeout(500)
            
            await page.keyboard.type(image, delay=50)
            log.info(f"✅ Typed image: {image}")
            
        except Exception as e:
            log.error(f"❌ فشل في الضغط وكتابة الرابط: {e}")
            raise RuntimeError(f"image_field_empty")
        
        await page.wait_for_timeout(3000)
        
        # ✅ 2. إعدادات الوصول و Create
        try:
            await page.get_by_role("radio", name="Allow public access").click(timeout=5000)
        except Exception:
            pass
            
        try:
            await page.get_by_role("radio", name="Instance-based").click(timeout=5000)
        except Exception:
            pass
            
        try:
            await page.get_by_role("button", name="Hide").click(timeout=2000)
        except Exception:
            pass
                
        await page.keyboard.press("End")
        await page.wait_for_timeout(1000)
        
        try:
            create_btn = page.get_by_role("button", name="Create")
            await create_btn.click(force=True, timeout=8000)
            log.info("✅ Create clicked")
        except Exception as e:
            log.error(f"❌ فشل في اختيار الإعدادات أو ضغط Create: {e}")
            raise RuntimeError("step4_failed")

        # ✅ 3. التحقق من الأخطاء
        await page.wait_for_timeout(5000)
        
        body_text = (await page.locator("body").inner_text()).lower()
        
        if "already exists" in body_text or "service name is already in use" in body_text:
            raise RuntimeError("service_already_exists")
            
        if "run/create" in page.url and "run/details" not in page.url:
            raise RuntimeError("google_error")

    async def step5_get_deployed_url(self, page):
        link_locator = page.locator('a[href*="run.app"]')
        try:
            await link_locator.wait_for(state="visible", timeout=60000)
            return await link_locator.get_attribute("href")
        except Exception:
            raise RuntimeError("ما لقيناش رابط run.app")
