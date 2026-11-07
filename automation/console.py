import asyncio
from playwright.async_api import expect
from utils.logger import get_logger

log = get_logger("Console")

class CloudConsole:
    def __init__(self, context):
        self.context = context

    async def step1_welcome_screen(self, page):
        await page.wait_for_load_state("networkidle")
        await page.wait_for_timeout(2000)    
        await page.keyboard.press("Enter")
        try:
            button = page.locator("text='I understand'")
            if await button.is_visible(timeout=3000):
                await button.click()
        except: pass
        await page.wait_for_load_state("networkidle")

    async def step2_tos_and_country(self, page):
        agree_btn = page.get_by_role("button", name="Agree and continue")
        try:
            await agree_btn.wait_for(state="visible", timeout=8000)
            checkboxes = page.get_by_role("checkbox")
            if await checkboxes.count() >= 2:
                await checkboxes.nth(0).click()
                await asyncio.sleep(0.5)
                await checkboxes.nth(1).click()
            await agree_btn.click()
            await page.wait_for_load_state("domcontentloaded")
        except Exception:
            pass

    async def step3_enable_api(self, page, project_id, authuser):
        api_url = f"https://console.cloud.google.com/apis/library/run.googleapis.com?project={project_id}&authuser={authuser}"
        await page.goto(api_url, wait_until="domcontentloaded")
        await page.wait_for_timeout(3000)
        
        enable_btn = page.get_by_role("button", name="Enable")
        manage_btn = page.get_by_role("button", name="Manage")
        
        try:
            await expect(enable_btn.or_(manage_btn)).to_be_visible(timeout=15000)
            if await enable_btn.is_visible():
                await enable_btn.click(timeout=10000)
                await expect(manage_btn).to_be_visible(timeout=60000)
        except Exception as e:
             log.warning(f"⚠️ مشكل فـ API: {e}")

    async def step4_create_cloud_run(self, page, project_id, authuser, image):
        try:
            # محاولة إيجاد الحقل بطرق مختلفة
            label = page.get_by_text("Container Image URL").first
            await label.wait_for(state="visible", timeout=20000)
            await label.click(timeout=10000)
            await page.wait_for_timeout(500)
            await page.keyboard.type(image, delay=50)
        except Exception as e:
            # إلا ما لقاش الحقل، يرمي خطأ واضح
            raise Exception(f"فشل إدخال صورة الحاوية. تحقق من سرعة النت أو تغيير الواجهة. ({str(e)[:100]})")
        
        await page.wait_for_timeout(3000)
        
        try:
            await page.get_by_role("radio", name="Allow public access").click(timeout=8000)
            await page.get_by_role("radio", name="Instance-based").click(timeout=8000)
            try:
                await page.get_by_role("button", name="Hide").click(timeout=2000)
            except: pass
            await page.keyboard.press("End")
            await page.wait_for_timeout(1000)
            
            create_btn = page.get_by_role("button", name="Create")
            await create_btn.click(force=True, timeout=15000)
        except Exception as e:
            raise Exception(f"فشل ضغط زر Create: {str(e)[:100]}")

    async def step5_get_deployed_url(self, page):
        try:
            link_locator = page.locator('a[href*="run.app"]')
            await link_locator.wait_for(state="visible", timeout=120000) 
            return await link_locator.get_attribute("href")
        except Exception as e:
            raise Exception(f"انتهى الوقت بدون ظهور رابط الخدمة (120 ثانية)")
