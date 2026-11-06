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
            await page.wait_for_load_state("networkidle", timeout=10000)
            await page.wait_for_timeout(2000)
            try: await page.keyboard.press("Enter")
            except: pass
            try:
                button = page.locator("text='I understand'").first
                if await button.is_visible(timeout=3000):
                    await button.click()
            except: pass
        except Exception as e:
            log.warning(f"⚠️ step1: {e}")

    async def step2_terms_dialog(self, page):
        log.info("🚀 step2: Terms Dialog")
        agree_btn = page.get_by_role("button", name="Agree and continue")
        try:
            await agree_btn.wait_for(state="visible", timeout=10000)
            checkboxes = page.get_by_role("checkbox")
            try:
                cnt = await checkboxes.count()
                if cnt >= 2:
                    await checkboxes.nth(0).click()
                    await asyncio.sleep(1)
                    await checkboxes.nth(1).click()
                elif cnt == 1:
                    await checkboxes.nth(0).click()
            except: pass
            await agree_btn.click()
            await page.wait_for_timeout(3000)
        except Exception as e:
            log.warning(f"⚠️ Terms Dialog: {e}")

    async def step3_enable_api(self, page, project_id, authuser):
        log.info("🚀 step3: Enable API")
        api_url = f"https://console.cloud.google.com/apis/library/run.googleapis.com?project={project_id}&authuser={authuser}"
        
        for attempt in range(3):
            try:
                await page.goto(api_url, wait_until="domcontentloaded", timeout=30000)
                break
            except Exception as e:
                if "ERR_ABORTED" in str(e) or "frame was detached" in str(e):
                    log.warning(f"⚠️ ERR_ABORTED فـ API، إعادة المحاولة {attempt+1}...")
                    await page.wait_for_timeout(3000)
                else:
                    raise e

        await page.wait_for_timeout(3000) 
        
        enable_btn = page.get_by_role("button", name="Enable")
        manage_btn = page.get_by_role("button", name="Manage")
        disable_btn = page.get_by_text("Disable API")

        try:
            await expect(enable_btn.or_(manage_btn)).to_be_visible(timeout=15000)
            if await enable_btn.is_visible():
                await enable_btn.click()
                try:
                    await expect(manage_btn.or_(disable_btn)).to_be_visible(timeout=20000)
                except: pass
        except Exception as e:
            log.warning(f"⚠️ step3: {e}")

    async def step4_create_cloud_run(self, page, project_id, authuser, image, region="europe-west1"):
        log.info(f"🌐 step4: إنشاء Cloud Run — region={region}")
        run_url = f"https://console.cloud.google.com/run/create?project={project_id}&authuser={authuser}&region={region}"
        
        for attempt in range(3):
            try:
                await page.goto(run_url, wait_until="domcontentloaded", timeout=60000)
                break
            except Exception as e:
                if "ERR_ABORTED" in str(e) or "frame was detached" in str(e):
                    log.warning(f"⚠️ ERR_ABORTED فـ Cloud Run، إعادة المحاولة {attempt+1}...")
                    await page.wait_for_timeout(3000)
                else:
                    raise e

        await page.wait_for_timeout(8000) 

        # ✅ فحص مبكر للخطأ
        error_text = await page.evaluate("""
            () => {
                const body = document.body.innerText.toLowerCase();
                if (body.includes('service with this name already exists') || body.includes('already exists')) return 'service_already_exists';
                return null;
            }
        """)
        if error_text: raise RuntimeError(error_text)

        # ✅ تعمير حقل الحاوية بلا ما نبدلو اسم الخدمة
        try:
            image_input = page.locator('input[aria-label*="Container Image URL" i]').first
            await image_input.wait_for(state="visible", timeout=15000)
            await image_input.click()
            await page.wait_for_timeout(500)
            await page.keyboard.press("Control+A")
            await page.keyboard.press("Backspace")
            await page.keyboard.type(image, delay=50)
        except Exception as e:
            log.error(f"❌ فشل في إدخال صورة الدوكر: {e}")
            raise RuntimeError("image_field_empty")

        await page.wait_for_timeout(3000) 

        try:
            try: await page.get_by_role("radio", name="Allow public access").click(timeout=5000)
            except: pass
            try: await page.get_by_role("radio", name="Instance-based").click(timeout=5000)
            except: pass
            try: await page.get_by_role("button", name="Hide").click(timeout=2000)
            except: pass
            
            await page.keyboard.press("End")
            await page.wait_for_timeout(1000)
            
            create_btn = page.get_by_role("button", name="Create")
            await create_btn.click(force=True, timeout=5000)
        except Exception as e:
            log.error(f"❌ فشل في ضغط Create: {e}")
            raise RuntimeError("step4_failed")

        # ✅ فحص سريع جدا للخطأ بعد الضغط على Create
        for _ in range(8): 
            await page.wait_for_timeout(500)
            error_text = await page.evaluate("""
                () => {
                    const body = document.body.innerText.toLowerCase();
                    if (body.includes('already exists') || body.includes('service with this name')) return 'service_already_exists';
                    if (body.includes('make sure all fields are correct') || body.includes('container image url is required')) return 'invalid_docker_image';
                    return null;
                }
            """)
            if error_text: raise RuntimeError(error_text)
            if "run/create" not in page.url: return 

        raise RuntimeError("invalid_docker_image")

    async def step5_get_deployed_url(self, page):
        log.info("⏳ step5: انتظار الرابط")
        for i in range(40):
            try:
                error_text = await page.evaluate("""
                    () => {
                        const body = document.body.innerText.toLowerCase();
                        if (body.includes('service with this name already exists') || body.includes('already exists')) return 'service_already_exists';
                        if (body.includes('deployment failed') || body.includes('revision is not ready')) return 'deployment_failed';
                        return null;
                    }
                """)
                if error_text: raise RuntimeError(error_text)

                url = await page.evaluate("""
                    () => {
                        const links = document.querySelectorAll('a');
                        for (const a of links) {
                            const href = a.href || '';
                            if (href.includes('.run.app')) return href.split('?')[0].split('#')[0];
                        }
                        return null;
                    }
                """)
                if url: return url
            except Exception as e:
                if "service_already_exists" in str(e) or "deployment_failed" in str(e): raise

            await page.wait_for_timeout(2000)
            if (i + 1) % 15 == 0:
                try: await page.reload(wait_until="domcontentloaded", timeout=30000)
                except: pass

        raise RuntimeError("timeout_waiting_for_url")
