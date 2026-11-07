import re
import asyncio
import os
from urllib.parse import urlparse
from automation.console import CloudConsole
from automation.api_deployer import deploy_cloud_run
from utils.logger import get_logger

log = get_logger("SSOFlow")

def extract_project_id(url: str) -> str:
    m = re.search(r'(qwiklabs-gcp-[\w-]+)', url or "")
    return m.group(1) if m else None

def extract_domain_from_service_url(service_url: str) -> str:
    s = (service_url or "").strip()
    if s.startswith("http://") or s.startswith("https://"):
        return urlparse(s).netloc.strip()
    return s.replace("http://", "").replace("https://", "").split("/")[0].strip()

async def run_sso_flow(context, bot, chat_id, sso_url: str, status_msg=None, password=None):
    project_id = extract_project_id(sso_url)
    if not project_id:
        return {"success": False, "error": "❌ Project ID في الرابط."}

    console = CloudConsole(context)
    page = None
    access_token = None

    async def update_msg(text):
        if status_msg:
            try: await status_msg.edit_text(text)
            except: pass

    # ✅ دالة التصوير
    async def take_screenshot(caption_text):
        if not page or page.is_closed(): return
        try:
            path = f"/tmp/shot_{int(asyncio.get_event_loop().time()*1000)}.jpg"
            await page.screenshot(path=path, full_page=False, type="jpeg", quality=70, timeout=5000)
            with open(path, "rb") as f:
                await bot.send_photo(chat_id=chat_id, photo=f, caption=caption_text)
            os.remove(path)
        except Exception as e:
            log.warning(f"⚠️ فشل إرسال صورة {caption_text}: {e}")

    def capture_token(request):
        nonlocal access_token
        if access_token: return
        try:
            auth = request.headers.get("authorization") or request.headers.get("Authorization")
            if auth and auth.startswith("Bearer "):
                access_token = auth.replace("Bearer ", "").strip()
                log.info("✅ تم التقاط الـ Token بنجاح!")
        except Exception:
            pass

    try:
        page = await context.new_page()
        page.on("request", capture_token)
        
        # ✅ الخطوة 1: فتح الرابط
        await update_msg("1) فتح رابط الطالب...")
        try: await page.goto(sso_url, wait_until="domcontentloaded", timeout=60000)
        except: await page.goto(sso_url, wait_until="commit", timeout=60000)
        await page.wait_for_timeout(3000)
        await take_screenshot("📸 الخطوة 1: فتح الرابط")
        
        # ✅ الخطوة 2: تسجيل الدخول / الباسورد
        await update_msg("2) جاري تسجيل الدخول...")
        try:
            password_input = page.locator('input[type="password"]').first
            if await password_input.is_visible(timeout=3000):
                if not password:
                    await take_screenshot("📸 الخطوة 2: يتطلب كلمة سر")
                    return {"success": False, "error": "need_password"}
                await password_input.fill(password)
                await page.wait_for_timeout(500)
                await page.keyboard.press("Enter")
                await page.wait_for_timeout(5000)
        except Exception as e:
            log.info(f"تجاوز الباسورد: {e}")
        await take_screenshot("📸 الخطوة 2: بعد تسجيل الدخول")

        # ✅ الخطوة 3: التوجيهات (TOS)
        await update_msg("3) قبول التوجيهات...")
        await console.step1_welcome_screen(page)
        try:
            await page.wait_for_url("**/home/dashboard**", timeout=45000)
        except Exception as e:
            log.warning(f"⚠️ ما وصلناش Dashboard: {e}")
        await take_screenshot("📸 الخطوة 3: بعد قبول التوجيهات (TOS)")

        # ✅ الخطوة 4: الشروط (Terms)
        await update_msg("4) قبول الشروط...")
        await console.step2_tos_and_country(page)
        await page.wait_for_timeout(2000)
        await take_screenshot("📸 الخطوة 4: بعد قبول الشروط")

        # --- استخراج التوكن والنشر ---
        await update_msg("5) استخراج Token...")
        await page.wait_for_timeout(3000)
        
        if not access_token:
            try:
                await page.evaluate("""
                    async () => {
                        try {
                            await fetch('https://cloudresourcemanager.googleapis.com/v1/projects', {
                                headers: { 'Accept': 'application/json' }
                            });
                        } catch (e) {}
                    }
                """)
                await page.wait_for_timeout(3000)
            except: pass

        if not access_token:
            try:
                access_token = await page.evaluate("""
                    () => {
                        try { return window.gapi.auth.getToken().access_token; } catch(e) {}
                        try { return window.gapi.auth2.getAuthInstance().currentUser.get().getAuthResponse().access_token; } catch(e) {}
                        return null;
                    }
                """)
            except: pass

        if not access_token:
            return {"success": False, "error": "❌ فشل استخراج Token."}

        await update_msg("6) جاري النشر عبر API...")
        final_url = await asyncio.to_thread(deploy_cloud_run, project_id, access_token)
        domain = extract_domain_from_service_url(final_url)

        return {"success": True, "domain": domain}

    except Exception as e:
        err_str = str(e)
        log.error(f"❌ خطأ: {err_str}")
        if page and not page.is_closed():
            await take_screenshot(f"📸 تفاصيل الخطأ: {err_str[:100]}")
        return {"success": False, "error": err_str}
    finally:
        if page:
            try: await page.close()
            except: pass
