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
        except Exception:
            pass
        await page.wait_for_load_state("networkidle")

    async def step2_tos_and_country(self, page):
        agree_btn = page.get_by_role("button", name="Agree and continue")
        try:
            await agree_btn.wait_for(state="visible", timeout=10000)
            checkboxes = page.get_by_role("checkbox")
            if await checkboxes.count() >= 2:
                await checkboxes.nth(0).click()
                await asyncio.sleep(1)
                await checkboxes.nth(1).click()
            await agree_btn.click()
            await page.wait_for_load_state("domcontentloaded")
        except Exception:
            pass

    async def step3_enable_api(self, page, project_id, authuser):
        api_url = f"https://console.cloud.google.com/apis/library/run.googleapis.com?project={project_id}&authuser={authuser}"
        await page.goto(api_url, wait_until="domcontentloaded")
        
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
        except Exception:
            pass

    async def step4_fill_fields(self, page, project_id, authuser, image):
        run_url = f"https://console.cloud.google.com/run/create?project={project_id}&authuser={authuser}"
        await page.goto(run_url, wait_until="domcontentloaded")
        await page.wait_for_timeout(5000)
        
        try:
            label = page.get_by_text("Container Image URL").first
            await label.click(timeout=10000)
            await page.wait_for_timeout(500)
            await page.keyboard.type(image, delay=50)
        except Exception as e:
            raise Exception(f"FIELD_ERROR: {str(e)}")
        
        await page.wait_for_timeout(3000)

    async def step4_part2_crater(self, page):
        try:
            await page.get_by_role("radio", name="Allow public access").click(timeout=8000)
            await page.get_by_role("radio", name="Instance-based").click(timeout=8000)
            try:
                await page.get_by_role("button", name="Hide").click(timeout=2000)
            except Exception:
                pass
            await page.keyboard.press("End")
            await page.wait_for_timeout(1000)
            
            create_btn = page.get_by_role("button", name="Create")
            await create_btn.click(force=True, timeout=15000)
            
            # التحقق من وجود خطأ الخدمة الموجودة مسبقاً
            await page.wait_for_timeout(4000)
            if await page.get_by_text("Service with this name already exists").is_visible():
                raise Exception("SERVICE_EXISTS")
        except Exception as e:
            if "SERVICE_EXISTS" in str(e):
                raise e
            raise Exception(f"CREATE_ERROR: {str(e)}")

    async def step5_get_deployed_url(self, page):
        try:
            link_locator = page.locator('a[href*="run.app"]')
            await link_locator.wait_for(state="visible", timeout=120000) 
            return await link_locator.get_attribute("href")
        except Exception:
            raise Exception("TIMEOUT_URL")
