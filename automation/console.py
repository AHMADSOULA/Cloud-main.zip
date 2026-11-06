"""
automation/console.py
كل خطوات Google Cloud Console — صامت (بلا تقارير، بلا تصوير)
"""
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

    # ═══════════════════════════════════════
    # دالة تصوير الشاشة وإرسالها (اللي كانت ناقصة)
    # ═══════════════════════════════════════
    async def _shot(self, page, caption: str = ""):
        """تصوير الشاشة وإرسالها للمستخدم (بكابسيون خاوي إلا بغيتي)"""
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
                except Exception as e:
                    log.warning(f"⚠️ send_photo: {e}")
            try:
                os.remove(path)
            except Exception:
                pass
        except Exception as e:
            log.warning(f"⚠️ _shot: {e}")

    # ═══════════════════════════════════════
    # STEP 1: TOS الأولى
    # ═══════════════════════════════════════

    async def step1_welcome_screen(self, page):
        log.info("🚀 step1: Welcome / TOS")
        try:
            await page.wait_for_load_state("domcontentloaded", timeout=10000)
            await page.wait_for_timeout(1500)
            try:
                await page.keyboard.press("Enter")
            except Exception:
                pass
            try:
                button = page.locator("text='I understand'").first
                if await button.is_visible(timeout=3000):
                    await button.click()
                    log.info("✅ I understand clicked")
            except Exception:
                pass
        except Exception as e:
            log.warning(f"⚠️ step1: {e}")

    # ═══════════════════════════════════════
    # STEP 2: Terms Dialog
    # ═══════════════════════════════════════

    async def step2_terms_dialog(self, page):
        log.info("🚀 step2: Terms Dialog")
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
            await page.wait_for_timeout(2000)
        except Exception as e:
            log.warning(f"⚠️ Terms Dialog: {e}")

    # ═══════════════════════════════════════
    # STEP 3: Enable API
    # ═══════════════════════════════════════

    async def step3_enable_api(self, page, project_id, authuser):
        log.info("🚀 step3: Enable API")
        api_url = f"https://console.cloud.google.com/apis/library/run.googleapis.com?project={project_id}&authuser={authuser}"
        await page.goto(api_url, wait_until="domcontentloaded", timeout=30000)
        await page.wait_for_timeout(2500)

        enable_btn = page.get_by_role("button", name="Enable")
        manage_btn = page.get_by_role("button", name="Manage")
        disable_btn = page.get_by_text("Disable API")

        try:
            await expect(enable_btn.or_(manage_btn)).to_be_visible(timeout=15000)
            if await enable_btn.is_visible():
                log.info("⏳ تفعيل API...")
                await enable_btn.click()
                try:
                    await expect(manage_btn.or_(disable_btn)).to_be_visible(timeout=60000)
                    log.info("✅ تم تفعيل API")
                except Exception:
                    pass
            elif await manage_btn.is_visible():
                log.info("ℹ️ API مفعل من قبل")
        except Exception as e:
            log.warning(f"⚠️ step3: {e}")

    # ═══════════════════════════════════════
    # STEP 4: Create Cloud Run (الطريقة الناجحة)
    # ═══════════════════════════════════════

    async def step4_create_cloud_run(self, page, project_id, authuser, image, region="us-central1"):
        run_url = f"https://console.cloud.google.com/run/create?project={project_id}&authuser={authuser}&region={region}"
        log.info(f"🌐 step4: إنشاء Cloud Run — region={region}")
        
        await page.goto(run_url, wait_until="domcontentloaded", timeout=60000)
        await page.wait_for_timeout(6000)

        try:
            label = page.get_by_text("Container Image URL").first
            await label.click(timeout=10000)
            await page.wait_for_timeout(500)
            await page.keyboard.press("Control+A")
            await page.keyboard.press("Backspace")
            await page.keyboard.type(image, delay=50)
            log.info(f"✅ تم كتابة صورة الدوكر: {image}")
        except Exception as e:
            log.error(f"❌ فشل في إدخال صورة الدوكر: {e}")
            raise RuntimeError("image_field_empty")

        await page.wait_for_timeout(3000)

        try:
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

            create_btn = page.get_by_role("button", name="Create")
            await create_btn.click(force=True, timeout=8000)
            log.info("✅ Create clicked")
            
        except Exception as e:
            log.error(f"❌ فشل في ضغط Create: {e}")
            raise RuntimeError("step4_failed")

        await page.wait_for_timeout(5000)
        
        try:
            body_text = (await page.locator("body").inner_text()).lower()
            if "already exists" in body_text or "service name is already in use" in body_text:
                log.error("❌ الخدمة كاينة بالفعل!")
                raise RuntimeError("service_already_exists")
            if "run/create" in page.url and "run/details" not in page.url:
                log.error("❌ البوت مازال معلق فصفحة الإنشاء (خطأ غير معروف)")
                raise RuntimeError("google_error")
        except Exception:
            pass

    # ═══════════════════════════════════════
    # STEP 5: Get URL
    # ═══════════════════════════════════════

    async def step5_get_deployed_url(self, page):
        log.info("⏳ step5: انتظار الرابط")
        for i in range(40):
            try:
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
                if url:
                    return url

                url = await page.evaluate("""
                    () => {
                        const body = document.body.innerText || '';
                        const m = body.match(/https:\\/\\/[a-zA-Z0-9\\-]+\\.run\\.app/);
                        if (m) return m[0];
                        return null;
                    }
                """)
                if url:
                    return url
            except Exception:
                pass

            await page.wait_for_timeout(2500)

            if (i + 1) % 10 == 0:
                try:
                    await page.reload(wait_until="domcontentloaded", timeout=30000)
                    await page.wait_for_timeout(2500)
                except Exception:
                    pass

        raise RuntimeError("ما لقيناش رابط run.app")
