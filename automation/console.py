import asyncio
from playwright.async_api import expect
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
        log.info("🚀 step2: Terms Dialog (Country + Agree)")
        try:
            # ✅ نستناو شوية باش الديالوغ يبان
            await page.wait_for_timeout(3000)
            
            # 1. نختارو الدولة إلا كان كاين الـ Dropdown
            try:
                select_el = page.locator("select").first
                if await select_el.is_visible(timeout=3000):
                    options = await select_el.locator("option").all()
                    if len(options) > 1:
                        await select_el.select_option(index=1)
                        log.info("✅ تم اختيار الدولة")
                        await page.wait_for_timeout(1000)
            except:
                pass

            # 2. نضغطو على checkboxes بـ JavaScript باش نضمنو 100%
            try:
                await page.evaluate("""
                    () => {
                        const cbs = document.querySelectorAll('mat-checkbox, [role="checkbox"], input[type="checkbox"]');
                        cbs.forEach(cb => {
                            if (!cb.checked && cb.getAttribute('aria-checked') !== 'true') {
                                cb.click();
                            }
                        });
                    }
                """)
                await page.wait_for_timeout(1000)
            except:
                pass

            # 3. نضغطو على Agree and continue
            agree_btn = page.get_by_role("button", name="Agree and continue")
            try:
                await agree_btn.wait_for(state="visible", timeout=5000)
                await agree_btn.click(timeout=5000)
                log.info("✅ تم الضغط على Agree and continue")
            except:
                # fallback بجافاسكريبت إلا كان الزر معطل
                await page.evaluate("""
                    () => {
                        for (const el of document.querySelectorAll('button, [role="button"]')) {
                            const t = (el.innerText || '').trim().toLowerCase();
                            if (t.includes('agree and continue')) {
                                el.disabled = false;
                                el.removeAttribute('disabled');
                                el.click();
                            }
                        }
                    }
                """)
                log.info("✅ تم الضغط على Agree (JS fallback)")
            
            await page.wait_for_load_state("domcontentloaded")
            await page.wait_for_timeout(2000)
        except Exception as e:
            log.warning(f"⚠️ step2: {e}")

    async def step3_enable_api(self, page, project_id, authuser):
        log.info("🚀 step3: Enable API")
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
        except Exception as e:
             raise Exception(f"عطل في تفعيل API: {str(e)}")

    async def step4_create_cloud_run(self, page, project_id, authuser, image, region="europe-west1"):
        log.info(f"🌐 step4: إنشاء Cloud Run — region={region}")
        run_url = f"https://console.cloud.google.com/run/create?project={project_id}&authuser={authuser}&region={region}"
        await page.goto(run_url, wait_until="domcontentloaded")
        
        await page.wait_for_timeout(5000)
        
        try:
            label = page.get_by_text("Container Image URL").first
            await label.click(timeout=10000)
            await page.wait_for_timeout(500)
            await page.keyboard.type(image, delay=50)
        except Exception as e:
            raise Exception("فشل في إدخال صورة الحاوية")
        
        await page.wait_for_timeout(3000)
        
        try:
            try: await page.get_by_role("radio", name="Allow public access").click(timeout=8000)
            except: pass
            try: await page.get_by_role("radio", name="Instance-based").click(timeout=8000)
            except: pass
            try: await page.get_by_role("button", name="Hide").click(timeout=2000)
            except: pass
                
            await page.keyboard.press("End")
            await page.wait_for_timeout(1000)
            
            create_btn = page.get_by_role("button", name="Create")
            await create_btn.click(force=True, timeout=10000)
        except Exception as e:
            raise Exception("فشل في ضغط Create")

        await page.wait_for_timeout(3000)
        body_text = await page.evaluate("() => document.body.innerText.toLowerCase()")
        if "already exists" in body_text or "service with this name" in body_text:
            raise Exception("service_already_exists")
        if "make sure all fields are correct" in body_text:
            raise Exception("invalid_fields")

    async def step5_get_deployed_url(self, page):
        log.info("⏳ step5: انتظار الرابط")
        try:
            link_locator = page.locator('a[href*="run.app"]')
            await link_locator.wait_for(state="visible", timeout=120000) 
            return await link_locator.get_attribute("href")
        except Exception as e:
            raise Exception("انتهى وقت الانتظار للرابط")
