import asyncio
from playwright.async_api import expect
from utils.logger import get_logger

log = get_logger("Console")

class CloudConsole:
    def __init__(self, context):
        self.context = context

    # ✅ دالة مساعدة لإعادة المحاولة عند طيحان الصفحة
    async def _safe_goto(self, page, url, retries=3):
        for attempt in range(retries):
            try:
                await page.goto(url, wait_until="domcontentloaded", timeout=60000)
                return
            except Exception as e:
                if "Page crashed" in str(e) or "Target closed" in str(e):
                    log.warning(f"⚠️ Page crashed, إعادة المحاولة {attempt+1}...")
                    try:
                        await page.close()
                    except: pass
                    # إنشاء صفحة جديدة
                    page = await self.context.new_page()
                    await asyncio.sleep(2)
                else:
                    raise e
        raise Exception("فشل تحميل الصفحة بعد 3 محاولات")

    async def step1_welcome_screen(self, page):
        log.info("🚀 step1: TOS")
        await page.wait_for_load_state("domcontentloaded")
        await page.wait_for_timeout(1500)
        await page.keyboard.press("Enter")
        try:
            button = page.locator("text='I understand'")
            if await button.is_visible(timeout=3000):
                await button.click()
        except: pass

    async def step2_tos_and_country(self, page):
        log.info("🚀 step2: Terms Dialog")
        agree_btn = page.get_by_role("button", name="Agree and continue")
        try:
            await agree_btn.wait_for(state="visible", timeout=8000)
            checkboxes = page.get_by_role("checkbox")
            await checkboxes.nth(0).click()
            await asyncio.sleep(0.5)
            await checkboxes.nth(1).click()
            await agree_btn.click()
        except Exception:
            log.info("ℹ️ رسالة الشروط لم تظهر، تم التخطي تلقائياً.")

    async def step3_enable_api(self, page, project_id, authuser):
        log.info("🚀 step3: Enable API")
        api_url = f"https://console.cloud.google.com/apis/library/run.googleapis.com?project={project_id}&authuser={authuser}"
        await self._safe_goto(page, api_url)
        await page.wait_for_timeout(2000)
        
        enable_btn = page.get_by_role("button", name="Enable")
        manage_btn = page.get_by_role("button", name="Manage")
        disable_btn = page.get_by_text("Disable API")
        
        try:
            await expect(enable_btn.or_(manage_btn)).to_be_visible(timeout=10000)
            if await enable_btn.is_visible():
                await enable_btn.click(timeout=5000)
                try:
                    await expect(manage_btn.or_(disable_btn)).to_be_visible(timeout=10000)
                except:
                    log.warning("⚠️ API Enable خدما ولكن الواجهة ماغيرتش بسرعة، غادي نكملو.")
            elif await manage_btn.is_visible():
                pass
        except Exception as e:
            log.warning(f"⚠️ مشكل فـ API: {str(e)}")

    async def step4_create_cloud_run(self, page, project_id, authuser, image):
        log.info("🚀 step4: Create Cloud Run")
        run_url = f"https://console.cloud.google.com/run/create?project={project_id}&authuser={authuser}"
        await self._safe_goto(page, run_url)
        await page.wait_for_timeout(3000)
        
        try:
            label = page.get_by_text("Container Image URL").first
            await label.click(timeout=10000)
            await page.wait_for_timeout(500)
            await page.keyboard.type(image, delay=20)
        except Exception as e:
            raise Exception(f"فشل في إدخال صورة الحاوية: {str(e)}")
        
        await page.wait_for_timeout(1000)
        
        try:
            await page.get_by_role("radio", name="Allow public access").click()
            await page.get_by_role("radio", name="Instance-based").click()
            try:
                await page.get_by_role("button", name="Hide").click(timeout=1500)
            except: pass
            await page.keyboard.press("End")
            await page.wait_for_timeout(500)
            
            create_btn = page.get_by_role("button", name="Create")
            await create_btn.click(force=True)
        except Exception as e:
            raise Exception(f"فشل في ضغط Create: {str(e)}")

    async def step5_get_deployed_url(self, page):
        log.info("🚀 step5: انتظار الرابط")
        try:
            link_locator = page.locator('a[href*="run.app"]')
            await link_locator.wait_for(state="visible", timeout=90000)
            return await link_locator.get_attribute("href")
        except Exception as e:
            raise Exception(f"انتهى وقت الانتظار للرابط: {str(e)}")
